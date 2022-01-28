#!/usr/bin/env python3

import requests
import pathlib
import random
import click
import myltt
import json
import sys
import re
import os



ALLOWED_PHONE_NUM_PREFIXES = ["091", "092", "094", "095", "097"]



def get_credentials_path() -> str:
	home = str(pathlib.Path.home())

	if sys.platform == "win32":
		data_dir = f"{home}/AppData/Roaming"
	
	elif sys.platform == "darwin":
		data_dir = f"{home}/Library/Application Support"
	
	else:
		data_dir = f"{home}/.local/share"
	
	credentials_path = f"{data_dir}/pyltt/credentials.json"
	os.makedirs(os.path.dirname(credentials_path), exist_ok=True)
	
	return credentials_path

def get_credentials_dict() -> dict:
	try:
		with open(get_credentials_path(), "r", encoding="UTF-8") as file:
			return json.loads(file.read())

	except Exception:
		return {}

def update_credentials(credentials: dict) -> dict:
	try:
		file_path = get_credentials_path()
		with open(file_path, "w", encoding="UTF-8") as file:
			file.write(json.dumps(credentials, indent="\t"))
		
		return credentials

	except Exception:
		raise click.FileError(file_path)

def check_token_validity(token: str) -> bool:
	response = myltt.validate_token(token)
	valid = response.status_code == 200
	try:
		valid or click.echo(json.loads(response.text)["message"])
	
	finally:
		return valid

def update_token(credentials: dict) -> dict:
	click.echo("Updating token...")
	
	json_data = json.loads(handle_myltt_response(myltt.refresh_old_token(credentials["refresh_token"], credentials["client_id"], credentials["client_secret"])).text)

	credentials["token"] = json_data["access_token"]
	credentials["refresh_token"] = json_data["refresh_token"]

	return update_credentials(credentials)

def get_credentials_with_updated_token(credentials: dict) -> dict:
	if not check_token_validity(credentials["token"]):
		credentials = update_token(credentials)

	return credentials

def check_phone_num_validity(phone_num: str) -> bool:
	return len(phone_num) == 10 and phone_num[:3] in ALLOWED_PHONE_NUM_PREFIXES

def clean_num_input(input_num: str) -> str:
	east_nums_dict = {
		"٠": "0",
		"١": "1",
		"٢": "2",
		"٣": "3",
		"٤": "4",
		"٥": "5",
		"٦": "6",
		"٧": "7",
		"٨": "8",
		"٩": "9",
	}

	for key, value in east_nums_dict.items():
		input_num = input_num.replace(key, value)

	return re.sub("[^0-9]", "", input_num)

def sanatize_phone_num(phone_num: str) -> str:
	phone_num = clean_num_input(phone_num)
 
	if len(phone_num) >= 9 and len(phone_num) <= 14:
		if phone_num[:3] == "218":
			phone_num = phone_num.replace("218", "0", 1)
		
		elif phone_num[:5] == "00218":
			phone_num = phone_num.replace("00218", "0", 1)
		
		elif phone_num[0] == "9":
			phone_num = "0" + phone_num

	return phone_num

def isnumber(text: str) -> bool:
	try:
		float(text)
		return True

	except ValueError:
		return False

def append_unit(text: str, unit: str) -> str:
	return (text + f" {unit}") if isnumber(text) else text

def remove_seconds_from_time_str(time_str: str) -> str:
	try:
		time_str =  ":".join(time_str.split(":")[:2])
	
	finally:
		return time_str

def format_datetime(datetime: str) -> str:
	try:
		date, time = datetime.split(" ")
		date = date.replace("-", "/")
		time = remove_seconds_from_time_str(time)
		datetime = f"{date} at {time}"

	finally:
		return datetime 

def convert_cents_to_lyd_str(cents: str) -> str:
	return append_unit(str(round(int(cents) / 1000, 2)), "LYD")

def convert_bytes_to_gib(bytes_str: str) -> str:
	return str(round(int(bytes_str) / 1024 / 1024 / 1024, 2))

def check_if_signed_up(credentials: dict) -> bool:
	return ("token" in credentials)

def generate_device_id() -> str:
	return hex(random.randint(2 ** 32, 2 ** 64)).replace("0x", "")

def handle_myltt_response(response: requests.Response) -> requests.Response:
	json_data = json.loads(response.text)
	
	if "message" in json_data:
		response_message = json_data["message"]
	
	elif "error" in json_data and "message" in json_data["error"]:
		response_message = json_data["error"]["message"]

	else:
		response_message = None


	if response.status_code != 200:
		raise click.ClickException(response_message or "Unexpected response from server")
	
	else:
		response_message and click.echo(response_message)
	
	return response



class Group(click.Group):
	def parse_args(self, ctx, args):
		if len(args) > 0 and args[0] in self.commands and (len(args) == 1 or args[1] not in self.commands):
				args.insert(0, "")

		super(Group, self).parse_args(ctx, args)



@click.group(invoke_without_command=True)
@click.pass_context
def pyltt(ctx: click.core.Context) -> None:
	"""A FOSS CLI Alternative to The Official MyLTT App"""
	
	is_logged_in = check_if_signed_up(get_credentials_dict())
	if not ctx.invoked_subcommand:
		if is_logged_in:
			ctx.invoke(service)
		
		else:
			ctx.invoke(signup)
	
	elif ctx.invoked_subcommand != "signup" and not is_logged_in:
		raise click.ClickException("You have to sign up first")
	
	elif ctx.invoked_subcommand == "signup" and is_logged_in:
		if not click.confirm("Are you sure that you want to switch accounts? all of your services are going to be removed"):
			raise click.Abort()



@pyltt.command()
def signup() -> None:
	"""Create a MyLTT account with a mobile number"""

	device_id = generate_device_id()
	phone_num = sanatize_phone_num(click.prompt("Mobile number"))

	if not check_phone_num_validity(phone_num):
		raise click.ClickException("This is not a valid Libyan mobile number")

	handle_myltt_response(myltt.get_verification_code(phone_num, device_id))

	otp = str(click.prompt("Verification code", type=int))
 
	handle_myltt_response(myltt.verify_phone_num(otp, phone_num, device_id))

	json_data = json.loads(handle_myltt_response(myltt.signup(phone_num, device_id)).text)
	client_id = str(json_data["result"]["client_id"])
	client_secret = json_data["result"]["client_secret"]

	json_data = json.loads(handle_myltt_response(myltt.get_token(client_id, client_secret, phone_num, device_id)).text)
	token = json_data["access_token"]
	refresh_token = json_data["refresh_token"]

	credentials = {
		"device_id": device_id,
		"phone_num": phone_num,
		"client_id": client_id,
		"client_secret": client_secret,
		"token": token,
		"refresh_token": refresh_token,
		"services": {},
	}

	update_credentials(credentials)



@pyltt.command()
def delete_account() -> None:
	"""Terminate the account that you're logged into"""

	credentials = get_credentials_with_updated_token(get_credentials_dict())

	if click.confirm("Are you sure you want to terminate the account?"):
		handle_myltt_response(myltt.delete_account(credentials["token"]))
		os.remove(get_credentials_path())



@pyltt.group(cls=Group, invoke_without_command=True)
@click.argument('service-name', required=False)
@click.pass_context
def service(ctx: click.core.Context, service_name: str) -> None:
	"""Add, remove, modify, view, and control your services"""

	credentials = get_credentials_dict()
	
	if service_name:
		if ctx.invoked_subcommand not in ["add", "list-services"] and service_name not in credentials["services"].keys():
			raise click.ClickException(f"You don't have a service with the name \"{service_name}\"")
	
		elif not ctx.invoked_subcommand:
			ctx.invoke(status)

	else:
		if ctx.invoked_subcommand not in [None, "add", "list-services"]:
			raise click.ClickException("You must specify a service")
	
		elif not ctx.invoked_subcommand:
			ctx.invoke(list_services)


@service.command()
def list_services() -> None:
	"""Get a list of your services"""

	credentials = get_credentials_dict()

	if not credentials["services"]:
		raise click.ClickException("You don't have any services yet, try to add some")

	click.echo("Services list:")
	for key, value in credentials["services"].items():
		click.echo(f"  [*] {key} ({value['service_type']})")


@service.command()
@click.pass_context
def status(ctx: click.core.Context) -> None:
	"""Get information about a service"""

	credentials = get_credentials_with_updated_token(get_credentials_dict())

	service_name = ctx.parent.params["service_name"]
	service = credentials["services"][service_name]

	service_info = json.loads(handle_myltt_response(myltt.get_user_service_info(service["credentials"], service["service_id"], credentials["token"])).text)["result"]

	service_group_type = json.loads(handle_myltt_response(myltt.get_packages(service["package_category_id"])).text)["result"]["type"]

	header = ("=" * 25) + f"  {service_name} ({service_info['status']})  " + ("=" * 25)
	footer = "=" * len(header)

	click.echo(f"\n{header}\n")
	if "package" in service_info and service_info["package"]:

		click.echo(f"Package: {service_info['package']['name']} ({service_info['package']['status']})")

		if service_group_type == "internet":
			if service_info["package"]["type"] in ["monthly", "weekly", "daily"]:
				if "quota" in  service_info["balances"]:
					if "amount" in service_info["balances"]["quota"] and service_info['balances']['quota']['amount'].isdigit():
						click.echo(f"\tQuota: {append_unit(convert_bytes_to_gib(service_info['balances']['quota']['amount']), 'GiB')} out of {append_unit(service_info['package']['quota'], 'GiB')}")
					
					if "validDate" in service_info["balances"]["quota"]:
						click.echo(f"\tExpiration Date: {format_datetime(service_info['balances']['quota']['validDate'])}")

				if "offpeak" in service_info["package"] and service_info["package"]["offpeak"]["enabled"] and "offpeak" in service_info["balances"] and service_info["balances"]["offpeak"]:
					click.echo("")
					click.echo(f"\tOff-Peak Quota ({remove_seconds_from_time_str(service_info['package']['offpeak']['start_time'])} - {remove_seconds_from_time_str(service_info['package']['offpeak']['end_time'])}): {append_unit(convert_bytes_to_gib(service_info['balances']['offpeak']['amount']), 'GiB')} out of {append_unit(str(service_info['package']['offpeak']['quota_gb']), 'GiB')}")
					click.echo(f"\tOff-Peak Expiration Date: {format_datetime(service_info['balances']['offpeak']['validDate'])}")
				
				click.echo("")

		elif service_group_type == "phone":
			if service_info["package"]["type"] in ["monthly", "weekly", "daily"]:
	
				# TODO: add support
				
				click.echo("\tNo package due to the lack of support for phone services")
				
				try:
					file_name = "phone_details.json"
					with open(file_name, "w", encoding="UTF-8") as file:
						dump_content = {"package": service_info["package"], "balances": (service_info["balances"] if ("balances" in service_info) else {})}
						file.write(json.dumps(dump_content, indent="\t"))

					click.echo(f"\tJSON data was dumped to \"{file_name}\" instead")
					click.echo("\tif you want to help improve phone services support")
					click.echo("\tyou can upload the file in a GitHub issue on SafwanLjd/PyLTT")
				
				except Exception:
					click.echo(f"\ttried to dump JSON data instead, but couldn't access \"{file_name}\"")
				
				click.echo("")
	
	if "balances" in service_info and "credit" in service_info["balances"] and "amount" in service_info["balances"]["credit"] and service_info['balances']['credit']['amount']:
		click.echo(f"Balance: {convert_cents_to_lyd_str(service_info['balances']['credit']['amount'])}")
		click.echo(f"\tExpiration Date: {format_datetime(service_info['balances']['credit']['validDate'])}")

	click.echo(f"\n{footer}\n")


@service.command()
@click.argument('service-type', required=False, nargs=-1)
@click.pass_context
def add(ctx: click.core.Context, service_type: tuple) -> None:
	"""Add a service account"""

	service_type = " ".join(service_type)

	json_data = json.loads(handle_myltt_response(myltt.get_services()).text)
	services = json_data["result"]

	services_dict = {}
	for service in services:
		services_dict[service["name"]] = service["id"]

	service_names = services_dict.keys()
	if not service_type or service_type not in service_names:
		click.echo("Specify a valid service type...\n\navailable service types are:", err=True)
		
		for service_name in service_names:
			click.echo("  [*] " + service_name, err=True)
	
	else:
		credentials = update_credentials(get_credentials_dict())
		
		service_name = ctx.parent.params["service_name"] or click.prompt("What do you want to name this service", prompt_suffix="? ")
		if service_name in credentials["services"].keys():
			raise click.ClickException("You already have a service with this name")

		service_type_id = str(services_dict[service_type])
		json_data = json.loads(handle_myltt_response(myltt.get_service_info(service_type_id)).text)
		
		service_credentials = {}
		required_fields = json_data["result"]["required_fields"]
		required_fields.sort(key=lambda element: element["id"])
		for field in required_fields:
			user_input = click.prompt(field["label"])
			if "suffix" in field and not user_input.endswith(field["suffix"]):
				user_input += field["suffix"]
			service_credentials[field["name"]] = user_input
		

		json_data = json.loads(handle_myltt_response(myltt.add_service(service_type_id, service_name, service_credentials, credentials["token"])).text)
		service_id = str(json_data["result"]["service_id"])

		
		package_categories = json.loads(handle_myltt_response(myltt.get_package_categories()).text)["result"]
		category_id = ""
		for category in package_categories:
			if category["title"] == service_type:
				category_id = str(category["id"])

		if not category_id:
			raise click.ClickException("Couldn't get the service's category ID")
	

		service_info = {
			"service_type": service_type,
			"service_id": service_id,
			"package_category_id": category_id,
			"credentials": service_credentials
		}

		credentials["services"][service_name] = service_info

		update_credentials(credentials)


@service.command()
@click.pass_context
def remove(ctx: click.core.Context) -> None:
	"""Remove a service account from your services"""

	credentials = get_credentials_with_updated_token(get_credentials_dict())

	service_name = ctx.parent.params["service_name"]
	service = credentials["services"][service_name]

	handle_myltt_response(myltt.delete_service(service["service_id"], credentials["token"]))

	del credentials["services"][service_name]

	update_credentials(credentials)


@service.command()
@click.argument('service-new-name', required=False)
@click.pass_context
def rename(ctx: click.core.Context, service_new_name: str) -> None:
	"""Rename a service"""
	
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	
	service_name = ctx.parent.params["service_name"]
	service = credentials["services"][service_name]

	service_new_name = service_new_name or click.prompt("What do you want to rename this service to", prompt_suffix="? ")
	if service_new_name in credentials["services"].keys():
		raise click.ClickException("You already have a service with this name")

	handle_myltt_response(myltt.update_friendly_name(service_new_name, service["service_id"], credentials["token"]))

	credentials["services"][service_new_name] = credentials["services"].pop(service_name)

	update_credentials(credentials)


@service.command()
@click.argument('voucher', required=False)
@click.pass_context
def top_up(ctx: click.core.Context, voucher: str) -> None:
	"""Recharge your balance with a voucher card number"""

	credentials = get_credentials_with_updated_token(get_credentials_dict())
	
	service_name = ctx.parent.params["service_name"]
	service = credentials["services"][service_name]

	voucher = voucher or str(click.prompt("Voucher number", type=int))

	handle_myltt_response(myltt.recharge_voucher(voucher, service["credentials"], service["service_id"], credentials["token"]))


@service.command()
@click.pass_context
def auto_recharge(ctx: click.core.Context):
	"""auto package re-subsribtion"""

	credentials = get_credentials_with_updated_token(get_credentials_dict())

	service_name = ctx.parent.params["service_name"]
	service = credentials["services"][service_name]

	status = "ON" if bool(json.loads(handle_myltt_response(myltt.get_auto_recharge_status(service["service_id"], credentials["token"])).text)["result"]["auto_recharge_status"]) else "OFF"
	click.echo(f"Auto-Recharge: {status}")

	if click.confirm(f"Do you want to turn it {'off' if status == 'ON' else 'on'}"):
		handle_myltt_response(myltt.toggle_auto_recharge_status(service["service_id"], credentials["token"]))

@service.command()
@click.pass_context
def subscribe(ctx: click.core.Context) -> None:
	"""Subscribe to a package"""

	credentials = get_credentials_with_updated_token(get_credentials_dict())

	service_name = ctx.parent.params["service_name"]
	service = credentials["services"][service_name]

	category_id = service["package_category_id"]
	json_data = json.loads(handle_myltt_response(myltt.get_packages(category_id)).text)["result"]
	
	package_groups = json_data["groups"]
	packages_type = json_data["type"]

	packages_dict = {}
	iterations = 0
	for package_group in package_groups:
		group_type = package_group["type"]

		for package in package_group["packages"]:
			iterations += 1
			packages_dict[iterations] = package["id"]

			click.echo(f"[{iterations}] {package['title']}")
			
			if packages_type == "internet":
				click.echo(f"\tSpeed: {append_unit(package['speed'], 'Mb/s')}")

				if group_type in ["monthly", "weekly", "daily"]:
					click.echo(f"\tQuota: {append_unit(package['quota'], 'GiB')}")
					click.echo(f"\tPrice: {append_unit(package['price'], 'LYD')}")
	
				elif group_type == "payg":
					if "price_peak" in package:
						click.echo(f"\tPrice: {append_unit(package['price_peak'], 'LYD/GiB')}")
						if package["price_peak"] != package["price_off_peak"]:
							click.echo(f"\tPrice Off-Peak ({remove_seconds_from_time_str(package['off_peak_start_time'])} - {remove_seconds_from_time_str(package['off_peak_end_time'])}): {append_unit(package['price_off_peak'], 'LYD/GiB')}")

					else:
						click.echo(f"\tPrice: {append_unit(package['price'], 'LYD/GiB')}")

			elif packages_type == "phone":
				if group_type in ["monthly", "weekly", "daily"]:
					click.echo(f"\tCalls: {append_unit(package['minutes_quota'], 'Minutes')}")
					click.echo(f"\tSMS's: {package['sms_quota']}")
					click.echo(f"\tMMS's: {package['mms_quota']}")
					click.echo(f"\tInternt: {append_unit(package['gprs_quota'], 'MiB')}")
					click.echo(f"\tPrice: {append_unit(package['price'], 'LYD')}")
	
				elif group_type == "payg":
					click.echo(f"\tCalls Price: {append_unit(package['calls_price'], 'LYD/MIN')}")
					click.echo(f"\tSMS Price: {append_unit(package['sms_price'], 'LYD/MSG')}")
					click.echo(f"\tMMS Price: {append_unit(package['sms_price'], 'LYD/MSG')}")
			
			click.echo("")
	
	
	index = click.prompt(f"Package Number (1-{len(packages_dict)})", type=int)
	if index not in packages_dict:
		raise click.ClickException("Invalid Choice")
	
	package_id = packages_dict[index]
	
	if not click.confirm(f"Are you sure?", default=True):
		raise click.Abort()

	handle_myltt_response(myltt.subscribe_to_package(package_id, service["credentials"], service["service_id"], credentials["token"]))





if __name__ == "__main__":
	pyltt(prog_name="pyltt")