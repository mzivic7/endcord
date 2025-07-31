import base64
import json
import os
import re
import subprocess
import sys
import uuid

# default client properties
CLIENT_BUILD_NUMBER = 400453  # should only affect experimental features availability
USER_AGENT_WEB = "Mozilla/5.0 (%OS; rv:138.0) Gecko/20100101 Firefox/138.0"
USER_AGENT_DESKTOP = "Mozilla/5.0 (%OS) AppleWebKit/537.36 (KHTML, like Gecko) discord/0.0.101 Chrome/134.0.6998.205 Electron/35.3.0 Safari/537.36"
LINUX_UA_STRING = "X11; Linux x86_64"
WINDOWS_UA_STRING = "Windows NT %VER; Win64; x64"
MACOS_UA_STRING = "Machintos; Intel Mac OS X %VER"
WINDOWS_VER = 10.0
MACOS_VER = 15.3

if sys.platform == "linux":
    operating_system = "Linux"
elif sys.platform == "win32":
    operating_system = "Windows"
elif sys.platform == "darwin":
    operating_system = "Mac OS X"
else:
    operating_system = "Linux"

# probably wont work on windows, but im not addidng whole locale library for that
locale = os.environ.get("LC_ALL") or os.environ.get("LANG")
if locale:
    system_locale = locale.split(".")[0]
else:
    system_locale = "en_US"


def get_anonymous_properties():
    """
    Get anonymous client properties which might look more suspicious to discord.
    This is approximaately what web client sends.
    """
    data = {
        "os": operating_system,
        "browser": "Mozilla",
        "device": "",
        "system_locale": system_locale,
        "browser_user_agent": "",
        "browser_version": "",
        "os_version": "",
        "referrer": "",
        "referring_domain": "",
        "referrer_current": "",
        "referring_domain_current": "",
        "release_channel": "stable",
        "client_build_number": CLIENT_BUILD_NUMBER,
        "client_event_source": None,
        "has_client_mods": False,
        "client_launch_id": str(uuid.uuid4()),
        "client_heartbeat_session_id": str(
            uuid.uuid4()
        ),  # used for persisted analytics heartbeat
    }

    user_agent = adjust_user_agent_os(USER_AGENT_WEB, sys.platform, None)

    return add_user_agent(data, user_agent)


def get_default_properties():
    """
    Get default client properties which might look less suspicious to discord.
    This is approximately what desktop client sends.
    """
    arch = "x64"
    if sys.platform == "linux":
        os_version = subprocess.check_output(["uname", "-r"], text=True).strip()
    elif sys.platform == "win32":
        win_ver = sys.getwindowsversion()
        os_version = f"{win_ver.major}.{win_ver.minor}.{win_ver.build}"
    elif sys.platform == "darwin":
        output = subprocess.check_output(["sw_vers"], text=True)
        os_version = output.split("\n")[1].split(":\t")[1]
        arch = "arm64"  # guessing
    else:
        os_version = ""

    data = {
        "os": operating_system,
        "browser": "Discord Client",
        "release_channel": "stable",
        "os_version": os_version,
        "os_arch": arch,
        "app_arch": arch,
        "system_locale": system_locale,
        "has_client_mods": False,
        "browser_user_agent": "",
        "browser_version": "",
        "client_build_number": CLIENT_BUILD_NUMBER,
        "native_build_number": None,
        "client_event_source": None,
        "client_app_state": "unfocused",
        "client_launch_id": str(uuid.uuid4()),
        "client_heartbeat_session_id": str(uuid.uuid4()),
    }
    if sys.platform == "linux":
        data["window_manager"] = (
            os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
            + ","
            + os.environ.get("GDMSESSION", "unknown")
        )

    user_agent = adjust_user_agent_os(USER_AGENT_DESKTOP, sys.platform, os_version)

    return add_user_agent(data, user_agent)


def add_for_gateway(data):
    """Add extra data for gateway"""
    gateway_data = data.copy()
    gateway_data.update(
        {
            "client_app_state": "unfocused",
            "is_fast_connect": False,
        }
    )
    return gateway_data


def add_user_agent(data, user_agent):
    """Add browser user agent to client properties and extract browser version"""
    browser_version = ""
    if "Firefox" in user_agent:
        match = re.search(r"Firefox/([\d\.]+);", user_agent)
        if match:
            browser_version = match.group(1)
    if "Opera" in user_agent:
        match = re.search(r"Opera/([\d\.]+);", user_agent)
        if match:
            browser_version = match.group(1)
    if "Trident" in user_agent:
        match = re.search(r"Trident\/.*rv:([\d\.]+);", user_agent)
        if match:
            browser_version = match.group(1)
    if "Safari" in user_agent:
        match = re.search(r"Version/([\d\.]+).*Safari/;", user_agent)
        if match:
            browser_version = match.group(1)
    elif "Electron" in user_agent:
        match = re.search(r"Elelctron/([\d\.]+);", user_agent)
        if match:
            browser_version = match.group(1)
    else:
        match = re.search(r"Chrome/([\d\.]+);", user_agent)
        if match:
            browser_version = match.group(1)

    data["browser_user_agent"] = user_agent
    data["browser_version"] = browser_version

    return data


def adjust_user_agent_os(user_agent, platform, ver):
    """Adjust user agent string for specific os"""
    if platform == "win32":
        if not ver:
            ver = WINDOWS_VER
        ver = ".".join(ver.split(".")[:2])
        new_os = WINDOWS_UA_STRING.replace("%VER", ver)
    elif platform == "darwin":
        if not ver:
            ver = MACOS_VER
        ver = ver.replace(".", "_")
        new_os = MACOS_UA_STRING.replace("%VER", ver)
    else:
        new_os = LINUX_UA_STRING
    return user_agent.replace("%OS", new_os)


def encode_properties(data):
    """Encode properties dict into base64 string"""
    return base64.b64encode(
        json.dumps(data, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")
