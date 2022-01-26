#!/usr/bin/env python3

from collections import OrderedDict
import requests
import pathlib
import random
import click
import myltt
import json
import sys
import re
import os



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
		return { "active": False }

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
	
	refresh_token = credentials["refresh_token"]
	client_id = credentials["client_id"]
	client_secret = credentials["client_secret"]
	
	json_data = json.loads(handle_myltt_response(myltt.refresh_old_token(refresh_token, client_id, client_secret)).text)
	new_token = json_data["access_token"]
	new_refresh_token = json_data["refresh_token"]

	credentials["token"] = new_token
	credentials["refresh_token"] = new_refresh_token

	return update_credentials(credentials)

def get_credentials_with_updated_token(credentials: dict) -> dict:
	token = credentials["token"]
	if not check_token_validity(token):
		credentials = update_token(credentials)
	
	return credentials

def get_category_id(service_name: str) -> str:
	package_categories = json.loads(handle_myltt_response(myltt.get_package_categories()).text)["result"]
	for category in package_categories:
		if category["title"] == service_name:
			category_id = str(category["id"])
			break

	
	return category_id

def try_update_category_id(service_name: str, credentials: dict) -> str:
	category_id = get_category_id(service_name)
	
	if category_id:
		credentials["services"][service_name]["package_category_id"] = category_id
		update_credentials(credentials)
		return category_id

	else:
		raise click.ClickException(f"Couldn't get packages for the service type \"{service_name}\"")

def check_phone_num_validity(phone_num: str) -> bool:
	return len(phone_num) == 10 and phone_num[:3] in ["091", "092", "094", "095", "097"]	

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

def sanatize_speed(speed: str) -> str:
	if speed.isdigit():
		speed += " Mb/s"
	
	return speed

def sanatize_quota(quota: str) -> str:
	if quota.isdigit():
		quota += " GiB"
	
	return quota

def check_if_signed_up(credentials: dict) -> bool:
	try:
		return credentials["active"]

	except Exception:
		return False

def generate_device_id() -> str:
    return hex(random.randint(2 ** 32, 2 ** 64)).replace("0x", "")

def handle_myltt_response(response: requests.Response) -> requests.Response:
	json_data = json.loads(response.text)

	try:
		response_message = json_data["message"]
	
	except Exception:
		try:
			response_message = json_data["error"]["message"]
		
		except Exception:
			response_message = None


	if response.status_code != 200:
		raise click.ClickException(response_message or "Unexpected error")
	
	else:
		response_message and click.echo(response_message)
	
	return response





class Group(click.Group):
    def parse_args(self, ctx, args):
        if len(args) > 0 and args[0] in self.commands:
            if len(args) == 1 or args[1] not in self.commands:
                args.insert(0, '')
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

	otp = clean_num_input(click.prompt("Verification code"))
 
	handle_myltt_response(myltt.verify_phone_num(otp, phone_num, device_id))

	json_data = json.loads(handle_myltt_response(myltt.signup(phone_num, device_id)).text)
	
	client_id = str(json_data["result"]["client_id"])
	client_secret = json_data["result"]["client_secret"]

	json_data = json.loads(handle_myltt_response(myltt.get_token(client_id, client_secret, phone_num, device_id)).text)

	token = json_data["access_token"]
	refresh_token = json_data["refresh_token"]

	credentials = {
		"active": True,
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
	token = credentials["token"]

	if click.confirm("Are you sure you want to terminate the account?"):
		handle_myltt_response(myltt.delete_account(token))
		os.remove(get_credentials_path())



@pyltt.group(cls=Group, invoke_without_command=True)
@click.argument('service-name', required=False)
@click.pass_context
def service(ctx: click.core.Context, service_name: str) -> None:
	"""Add, remove, modify, view, and control your services"""

	credentials = get_credentials_dict()
	if (ctx.invoked_subcommand and ctx.invoked_subcommand not in ["add", "list-services"]) or (not ctx.invoked_subcommand and service_name):
		user_services = credentials["services"]
		service_names = list(user_services.keys())
		if not service_name in service_names:
			raise click.ClickException("Specify a valid service")

	if not ctx.invoked_subcommand:
		if service_name:
			ctx.invoke(status)
		
		else:
			ctx.invoke(list_services)


@service.command()
def list_services() -> None:
	"""Get a list of your services"""
	credentials = get_credentials_dict()
	user_services = credentials["services"]

	if not user_services:
		raise click.ClickException("You don't have any services yet, try to add some")

	click.echo("Services:")
	for key, value in user_services.items():
		click.echo(f"  [*] {key} ({value['service_type']})")


@service.command()
@click.pass_context
def status(ctx: click.core.Context) -> None:
	"""Get information about a service"""

	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	token = credentials["token"]
	user_services = credentials["services"]
	service = user_services[service_name]
	service_id = service["service_id"]
	service_credentials = service["credentials"]

	service_status = json.loads(handle_myltt_response(myltt.get_user_service_info(service_credentials, service_id, token)).text)["result"]
	
	header = ("=" * 25) + "  " + service_name + "  " + ("=" * 25)
	footer = "=" * len(header)

	click.echo("\n" + header + "\n")
	click.echo(f"Service Type: {service['service_type']} ({service_status['status']})")
	("username" in service_credentials) and click.echo(f"Service Account Username: {service_credentials['username']}")
	("number" in service_credentials) and click.echo(f"Service Number: {service_credentials['number']}")
	
	if "balances" in service_status and service_status["balances"]:
		click.echo("")
		if "credit" in service_status["balances"] and service_status["balances"]["credit"] and "amount" in service_status["balances"]["credit"] and service_status["balances"]["credit"]["amount"].isdigit() and "validDate" in service_status["balances"]["credit"]:
			click.echo("")
			click.echo(f"Current Balance: {round(int(service_status['balances']['credit']['amount']) / 1000, 2)} LYD")
			click.echo(f"Balance Expiration Date: {service_status['balances']['credit']['validDate']}")
		
		if "quota" in service_status["balances"] and service_status["balances"]["quota"] and "amount" in service_status["balances"]["quota"] and service_status["balances"]["quota"]["amount"].isdigit() and "validDate" in service_status["balances"]["quota"]:
			click.echo("")
			click.echo(f"Current Quota: {round(int(service_status['balances']['quota']['amount']) / 1024 / 1024 / 1024, 2)} GiB")
			click.echo(f"Qutoa Expiration Date: {service_status['balances']['quota']['validDate']}")
		
		if "offpeak" in service_status["balances"] and service_status["balances"]["offpeak"] and "amount" in service_status["balances"]["offpeak"] and service_status["balances"]["offpeak"]["amount"].isdigit() and "validDate" in service_status["balances"]["offpeak"]:
			click.echo("")
			click.echo(f"Current Off-Peak Quota: {round(int(service_status['balances']['offpeak']['amount']) / 1024 / 1024 / 1024, 2)} GiB")
			click.echo(f"Off-Peak Qutoa Expiration Date: {service_status['balances']['offpeak']['validDate']}")

	if "package" in service_status and service_status["package"]:
		click.echo("\n")
		click.echo(f"Current Package ({service_status['package']['status']}):\n")
		click.echo(f"  Package Name: {service_status['package']['name']} ({service_status['package']['type']})")		
		click.echo(f"  Package Max Speed: {sanatize_speed(service_status['package']['max_speed'])}")
		
		if "quota" in service_status["package"] and service_status['package']['quota']:
			click.echo(f"  Package Quota: {sanatize_quota(service_status['package']['quota'])}")
		
		if "offpeak" in service_status["package"] and service_status["package"]["offpeak"] and service_status["package"]["offpeak"]["enabled"]:
			click.echo(f"  Package Off-Peak Quota ({service_status['package']['offpeak']['start_time']} - {service_status['package']['offpeak']['end_time']}): {sanatize_quota(str(service_status['package']['offpeak']['quota_gb']))}")

	click.echo("\n" + footer + "\n")


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
		if "phone" not in service["name"].lower() and "hatif" not in service["name"].lower():
			services_dict[service["name"]] = service["id"]

	service_names_list = list(services_dict.keys())
	if not service_type or service_type not in service_names_list:
		click.echo("Specify a valid service type...\n\navailable service types are:", err=True)
		
		for service_name in service_names_list:
			click.echo("  [*] " + service_name, err=True)
	
	else:
		credentials = update_credentials(get_credentials_dict())
		user_services = credentials["services"]
		token  = credentials["token"]
		
		service_name = ctx.parent.params["service_name"] or click.prompt("What do you want to name this service", prompt_suffix="? ")
		
		if service_name in list(user_services.keys()):
			raise click.ClickException("You already have a service with this name")

		service_type_id = str(services_dict[service_type])
		json_data = json.loads(handle_myltt_response(myltt.get_service_info(service_type_id)).text)
		
		service_credentials = {}
		required_fields = json_data["result"]["required_fields"]
		required_fields.sort(key=lambda element: element["id"])
		for field in required_fields:
			user_input = click.prompt(field["label"], hide_input=(field["name"] in ["password", "pin", "lte_pin"]))
			if "suffix" in field and not user_input.endswith(field["suffix"]):
				user_input += field["suffix"]
			service_credentials[field["name"]] = user_input
		

		json_data = json.loads(handle_myltt_response(myltt.add_service(service_type_id, service_name, service_credentials, token)).text)
		service_id = str(json_data["result"]["service_id"])

		category_id = get_category_id(service_type)
	

		service_info = {
			"service_type": service_type,
			"service_id": service_id,
			"package_category_id": category_id,
			"credentials": service_credentials
		}

		user_services[service_name] = service_info
		credentials["services"] = user_services

		update_credentials(credentials)


@service.command()
@click.pass_context
def remove(ctx: click.core.Context) -> None:
	"""Remove a service account from your services"""

	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	token = credentials["token"]
	user_services = credentials["services"]
	service = user_services[service_name]
	service_id = service["service_id"]

	handle_myltt_response(myltt.delete_service(service_id, token))

	del user_services[service_name]
	credentials["services"] = user_services
	
	update_credentials(credentials)


@service.command()
@click.argument('new-service-name', required=False)
@click.pass_context
def rename(ctx: click.core.Context, new_service_name: str) -> None:
	"""Rename a service"""
	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	token = credentials["token"]
	user_services = credentials["services"]
	service = user_services[service_name]
	service_id = service["service_id"]

	new_service_name = new_service_name or click.prompt("What do you want to rename this service to", prompt_suffix="? ")
	if new_service_name in list(user_services.keys()):
		raise click.ClickException("You already have a service with this name")

	handle_myltt_response(myltt.update_friendly_name(new_service_name, service_id, token))

	user_services[new_service_name] = user_services.pop(service_name)
	credentials["services"] = user_services

	update_credentials(credentials)


@service.command()
@click.argument('voucher', required=False)
@click.pass_context
def top_up(ctx: click.core.Context, voucher: str) -> None:
	"""Recharge your balance with a voucher card number"""

	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	token = credentials["token"]
	user_services = credentials["services"]
	service = user_services[service_name]
	service_id = service["service_id"]
	service_credentials = service["credentials"]

	voucher = voucher or clean_num_input(click.prompt("Voucher number"))

	handle_myltt_response(myltt.recharge_voucher(voucher, service_credentials, service_id, token))


@service.command()
@click.pass_context
def auto_recharge(ctx: click.core.Context):
	"""auto package re-subsribtion"""

	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	token = credentials["token"]
	user_services = credentials["services"]
	service = user_services[service_name]
	service_id = service["service_id"]
	
	status = "ON" if bool(json.loads(handle_myltt_response(myltt.get_auto_recharge_status(service_id, token)).text)["result"]["auto_recharge_status"]) else "OFF"
	click.echo(f"Auto-Recharge: {status}")

	if click.confirm(f"Do you want to turn it {'off' if status == 'ON' else 'on'}"):
		handle_myltt_response(myltt.toggle_auto_recharge_status(service_id, token))


@service.command()
@click.pass_context
def packages(ctx: click.core.Context) -> None:
	"""List available packages for a service"""

	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_dict()
	user_services = credentials["services"]
	service = user_services[service_name]
	service_type = service["service_type"]
	category_id = service["package_category_id"] or try_update_category_id(service_name, credentials)

	package_groups = json.loads(handle_myltt_response(myltt.get_packages(category_id)).text)["result"]["groups"]

	packages_text = ""
	for package_group in package_groups:
		if len(package_group["packages"]) > 0:
			packages_text += f"{package_group['title']} ({package_group['type']}):\n"
		
		for package in package_group["packages"]:
			packages_text += f"  [*] {package['title']}:\n"
			
			if "price" in package:
				packages_text += f"        Price: {package['price']} LYD\n"
			
			if "quota" in package:				
				packages_text += f"        Quota: {sanatize_phone_num(package['quota'])}\n"
			
			packages_text += f"        Max Speed: {sanatize_speed(package['speed'])}\n"
			packages_text += f"        Package ID: {package['id']}\n"
			packages_text += "\n"
	
	click.echo_via_pager(packages_text)


@service.command()
@click.argument('package-id', required=False)
@click.pass_context
def subscribe(ctx: click.core.Context, package_id) -> None:
	"""Subscribe to a package"""

	service_name = ctx.parent.params["service_name"]
	credentials = get_credentials_with_updated_token(get_credentials_dict())
	token = credentials["token"]
	user_services = credentials["services"]
	service = user_services[service_name]
	service_id = service["service_id"]
	service_credentials = service["credentials"]

	if not package_id:
		category_id = service["package_category_id"] or try_update_category_id(service_name, credentials)
		package_groups = json.loads(handle_myltt_response(myltt.get_packages(category_id)).text)["result"]["groups"]

		packages = []
		for package_group in package_groups:			
			packages += package_group["packages"]
		
		packages_dict = OrderedDict()
		for i in range(len(packages)):
			package = packages[i]
			if "price" in package and "quota" in package:
				packages_title = f"{package['title']} ({sanatize_quota(package['quota'])}, {package['price']} LYD)"
				packages_dict[packages_title] = package["id"]
				click.echo(f"[{i + 1}]  {packages_title}")
		
		click.echo("")
		
		choice = clean_num_input(click.prompt(f"Package Number (1-{len(packages_dict)})"))
		index = (int(choice) - 1) if choice else -1

		if index < 0 or index >= len(packages_dict):
			raise click.ClickException("Invalid Choice")
		
		package_title = list(packages_dict.keys())[index]
		package_id = packages_dict[package_title]
		
		if not click.confirm(f"Are you sure you want to subscribe to \"{package_title}\"", default=True):
			raise click.Abort()

	handle_myltt_response(myltt.subscribe_to_package(package_id, service_credentials, service_id, token))





if __name__ == "__main__":
	pyltt(prog_name="pyltt")