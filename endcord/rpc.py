import json
import logging
import os
import socket
import struct
import threading

logger = logging.getLogger(__name__)
DISCORD_SOCKET = "/run/user/1000/discord-ipc-0"
DISCORD_ASSETS_WHITELIST = (   # assets passed from RPC app to discord as text
    "large_text",
    "small_text",
    "large_image",   # external images are text
    "small_image",
)

def receive_data(connection):
    """Receive and decode nicely packed json data"""
    header = connection.recv(8)
    try:
        op, length = struct.unpack("<II", header)
        data = connection.recv(length)
        final_data = json.loads(data)
        return op, final_data
    except struct.error as e:
        logger.error(e)
        return None, None


def send_data(connection, op, data):
    """
    Nicely encode and send json data.
    op codes:
    0 - handshake
    1 - payload
    """
    payload = json.dumps(data, separators=(",", ":"))
    package = struct.pack("<ii", op, len(payload)) + payload.encode("utf-8")
    connection.sendall(package)


class RPC:
    """Main RPC class"""

    def __init__(self, discord, user, config):
        if os.path.exists(DISCORD_SOCKET):
            os.unlink(DISCORD_SOCKET)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(DISCORD_SOCKET)
        self.discord = discord
        self.run = True
        self.changed = False
        self.external = config["rpc_external"]
        self.presences = []
        self.dispatch = {
            "cmd": "DISPATCH",
            "data": {
                "v": 1,
                "config": {
                    "cdn_host": "cdn.discordapp.com",
                    "api_endpoint": "//discord.com/api",
                    "environment": "production",
                },
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "discriminator": user["extra"]["discriminator"],
                    "global_name": user["global_name"],
                    "avatar": user["extra"]["avatar"],
                    "avatar_decoration_data": user["extra"]["avatar_decoration_data"],
                    "bot": False,
                    "flags": 32,
                    "premium_type": user["extra"]["premium_type"],
                },
            },
            "evt": "READY",
            "nonce": None,
        }


    def client_thread(self, connection):
        """Thread that handles receiving and sending data from one client"""
        app_id = None
        try:   # lets keep server running even if there is error in one thread
            logger.info("RPC client connected")
            op, init_data = receive_data(connection)
            app_id = init_data["client_id"]
            logger.debug(f"RPC app id: {app_id}")
            rpc_data = self.discord.get_rpc_app(app_id)
            rpc_assets = self.discord.get_rpc_app_assets(app_id)
            if rpc_data and rpc_assets:
                send_data(connection, 1, self.dispatch)
                while self.run:
                    op, data = receive_data(connection)
                    if not data:
                        break
                    logger.debug(f"Received: {json.dumps(data, indent=2)}")

                    if data["cmd"] == "SET_ACTIVITY":
                        activity = data["args"]["activity"]
                        activity_type = activity.get("type", 0)
                        # add everything thats missing
                        activity["application_id"] = app_id
                        activity["name"] = rpc_data["name"]
                        assets = {}
                        for asset_client in activity["assets"]:
                            # check if asset is external link
                            if activity["assets"][asset_client][:8] == "https://":
                                if self.external:
                                    external_asset = self.discord.get_rpc_app_external(app_id, activity["assets"][asset_client])
                                    assets[asset_client] = f"mp:{external_asset[0]["external_asset_path"]}"
                                else:
                                    external_asset = activity["assets"][asset_client]
                                continue
                            # check if asset is an image
                            elif "image" in asset_client:
                                for asset_app in rpc_assets:
                                    if activity["assets"][asset_client] == asset_app["name"]:
                                        assets[asset_client] = asset_app["id"]
                                        break
                            elif asset_client in DISCORD_ASSETS_WHITELIST:
                                    assets[asset_client] = activity["assets"][asset_client]
                                    continue
                        # multiply timestamps by 1000
                        if "timestamps" in activity:
                            if "start" in activity["timestamps"]:
                                activity["timestamps"]["start"] *= 1000
                            if "end" in activity["timestamps"]:
                                activity["timestamps"]["end"] *= 1000
                        activity["assets"] = assets
                        if activity_type == 2:
                            activity.pop("flags", None)
                        activity["flags"] = 1
                        activity["type"] = activity_type
                        activity.pop("instance", None)

                        # self.changed will be true only when presence data has been updated
                        for num, app in enumerate(self.presences):
                            if app["application_id"] == app_id:
                                if activity != self.presences[num]:
                                    self.presences[num] = activity
                                    self.changed = True
                                break
                        else:
                            self.presences.append(activity)
                            self.changed = True

                        response = {
                            "cmd": data["cmd"],
                            "data": data["args"]["activity"],
                            "evt": None,
                            "nonce": data["nonce"],
                        }
                        send_data(connection, op, response)
                    else:
                        # all other commands are curerntly unimplemented
                        # returning them to client so it can keep running with rich presence only
                        # this will probably create some errors with edge-case clients
                        response = {
                            "cmd": data["cmd"],
                            "data": {
                                "evt": data["evt"],
                            },
                            "evt": None,
                            "nonce": data["nonce"],
                        }
                        send_data(connection, op, response)

            else:
                logger.warn("Failed retrieving RPC app data from discord")
        except Exception as e:
            logger.error(e)
        # remove presence from list
        if app_id:
            for num, app in enumerate(self.presences):
                if app["application_id"] == app_id:
                    self.presences.pop(num)
                    self.changed = True
                    break
        logger.info("RPC client disconnected")
        connection.close()


    def server_thread(self):
        """Thread that listens for new connections on socket and starts new client_thread for each connection"""
        logger.info("RPC server started")
        while self.run:
            self.server.listen(1)
            client, address = self.server.accept()
            threading.Thread(target=self.client_thread, daemon=True, args=(client, )).start()


    def get_rpc(self):
        """Get RPC events for all connected apps, only when presence has changed."""
        if self.changed:
            self.changed = False
            logger.debug(f"Sending: {json.dumps(self.presences, indent=2)}")
            return self.presences
        return None
