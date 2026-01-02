import time
import json
import hmac

import requests

import ttgateway.commands as cmds
from ttgateway.config import config
from ttgateway.cli_client import CLIClient, error_style


class RemoteCliClient(CLIClient):
    """ Remote client, to access gateways through the backend. """
    def __init__(self, *args, **kwargs):
        super().__init__(startup=False, *args, **kwargs)
        h = hmac.new(key=self.key, msg=self.msg, digestmod="sha1")
        self.headers = {
            "user-agent": f"ttcli_remote/{config.VERSION}",
            "authorizationToken": h.hexdigest(),
        }
        self.device_id = ""
        self.connection_id = ""
        self.last_cmd_ts = 0

    @property
    def url(self):
        return config.remote_client_cli.url

    @property
    def key(self) -> bytes:
        return config.remote_client_cli.hmac_key.encode()

    @property
    def msg(self) -> bytes:
        return config.remote_client_cli.hmac_msg.encode()

    def select_device(self):
        url = f"{self.url}/connected-devices/"
        r = requests.get(url, headers=self.headers, timeout=(10,10))
        rsp = r.json()
        try:
            if rsp["devices"]:
                print("Connected devices:")
                for n, device in enumerate(rsp["devices"]):
                    print("\t{}: {}".format(n+1, device["deviceID"]))

                dev_len = len(rsp["devices"])
                while True:
                    prompt = "Select device number (1-{}): ".format(dev_len)
                    sel = input(prompt)
                    if (sel.isdecimal() and 0 < int(sel) <= dev_len):
                        break
                    print("Invalid selection \"{}\"".format(sel))
                    return None
                self.device_id = rsp["devices"][int(sel)-1]["deviceID"]
                self.connection_id = rsp["devices"][int(sel)-1]["connectionID"]
                print("Selected device: {} (Connection ID {})".format(
                    self.device_id, self.connection_id))
                return self.device_id
            print("No devices connected. Exiting...")
            return None
        except KeyboardInterrupt:
            print("Exiting...")
            return None

    def send_cmd(self, command: cmds.Command):
        payload = {
            "command": command.to_json(),
            "devices": [{
                    "deviceID": self.device_id,
                    "connectionID": self.connection_id,
                }],
        }

        self.last_cmd_ts = int(time.time())
        url = f"{self.url}/execute-command"
        requests.post(url, headers=self.headers, data=json.dumps(payload),
                timeout=(10,10))

    def recv_data(self, silent=False):
        resp = None
        start_ts = time.monotonic()
        while resp is None:
            time.sleep(0.2)
            url = f"{self.url}/last-commands/?deviceID={self.device_id}"
            r = requests.get(url, headers=self.headers, timeout=(10,10))
            for result in r.json()["result"]:
                if (result["deviceID"] == self.device_id
                        and int(result["createdAt"]) >= self.last_cmd_ts-1):
                    resp = json.loads(result["lastCommand"])
            if time.monotonic() - start_ts > 10:
                break

        if resp is None:
            if not silent:
                self.poutput("No response")
            return None

        if "info" in resp:
            if resp["success"]:
                if not silent:
                    self.poutput(resp["info"])
            else:
                if not silent:
                    self.poutput(error_style(resp["info"]))
        if "data" in resp:
            return resp["data"]
        return None
