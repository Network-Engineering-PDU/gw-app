import os
import json
from datetime import datetime as dt

# pylint: disable=line-too-long
default_config_dict = {
    "gateway": {
        "datetime_period": 86400,
        "battery_period": 86400,
        "telemetry_period": 600,
        "co2_period": 300,
        "pwmt_period": 300,
        "automation_get_period": 600,
        "automation_status_period": 600,
        "sleep_time": 43200,
        "ping_period": 120,
        "platform": "desktop",
        "node_db": "sqlite", # sqlite, memory
        "task_config": "legacy", # legacy, default
        "multi_gw_role": "fault", # standalone, server, passthrough, fault
    },
    "gw_local": [
        {
            "port": "/dev/ttymxc6",
        },
    ],
    "multi_gw_server": {
        "host": "192.168.0.1",
        "port": 31888,
        "ping_period": 120,
        "ca_cert": "/etc/tychetools/certs/ca.crt",
        "server_cert": "/etc/tychetools/certs/server.crt",
        "server_key": "/etc/tychetools/certs/server.key",
    },
    "multi_gw_client": {
        "ca_cert": "/etc/tychetools/certs/ca.crt",
        "client_cert": "/etc/tychetools/certs/client.crt",
        "client_key": "/etc/tychetools/certs/client.key",
    },
    "backend": {
        "url": "https://api.tychetools.com",
        "company": "company",
        "device_id": "112233445566",
        "user": "user@tychetools.com",
        "password": "password",
        "tel_period": 600,
        "bat_period": 86400,
        "pwmt_period": 300,
        "pol_period": 0,
        "bak_period": 600,
    },
    "air_quality": {
        "url": "https://iaq-api.tychetools.com",
        "client": "client",
        "user": "user@tychetools.com",
        "password": "password",
        "tel_period": 600,
        "iaq_period": 600,
        "bat_period": 86400,
        "data_timeout": 28800,
    },
    "csv": {
        "telemetry": True,
        "battery": True,
        "co2": True,
        "power_meter": True,
        "macs": [],
    },
    "influxdb": {
        "ip": "192.168.0.100",
        "token": "4rBM2s2QBIZOmYK_Gpo1tu-oDIcUuhV5B_AZxDWilVj9MMIa4o5v9rZrLL-J4bbVjDUrM0DgvsL7BpAE7CxQKQ==",
        "org": "tychetools",
        "bucket_name": "pwmt_bucket",
        "point_name": "telemetry",
        "tag_name": "node",
    },
    "mqtt": {
        "ip": "192.168.0.100",
        "port": 1883,
        "prefix": "tychetools",
    },
    "fault_manager": {
        "transport": "udp",
    },
    "remote_client": {
        "url": "wss://zljh915574.execute-api.eu-west-1.amazonaws.com",
        "hmac_key": "tych3t00ls2022#",
        "hmac_msg": "Websockets in Tychetools",
    },
    "remote_client_cli": {
        "url": "https://xwryr2cuji.execute-api.eu-west-1.amazonaws.com/dev",
        "hmac_key": "tych3t00ls2022$",
        "hmac_msg": "API REST in Tychetools",
    },
    "http_logging": {
        "url": "https://rumss5huy5zjoasb5f5zczld5m0dtjtv.lambda-url.eu-west-1.on.aws/",
        "period": 15,
    },
}
# pylint: enable=line-too-long

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

def dict_to_attr_dict(d):
    if isinstance(d, dict):
        a = AttrDict()
        for key, value in d.items():
            a[key] = dict_to_attr_dict(value)
        return a
    return d

class Config:
    VERSION = "1.14.3"
    LIB_VERSION = "1.12.2"
    TT_DIR = os.path.expanduser("~/.tychetools")
    CONFIG_FILE = f"{TT_DIR}/gw.config"
    GWRC_FILE = f"{TT_DIR}/gwrc"
    DAEMON_PID_FILE = "/tmp/ttgw.pid"
    SERVER_SOCKET = "/tmp/ttgw.socket"
    BLE_SOCKET = "/tmp/ble.socket"
    SNMP_SOCKET = "/tmp/ttgw_snmp.socket"
    HOSTNAME_FILE = os.path.expanduser("~/hostname")

    def __init__(self):
        self.loaded = False
        self.config = dict_to_attr_dict(default_config_dict)
#pylint: disable=no-member
        self.config.gateway.platform = self.get_platform()
#pylint: enable=no-member

        self.default_gwrc = [
            "fault enable",
            "app enable backend",
            "start_remote_client",
            "start_http_logging",
        ]
        self.default_negwrc = [
            "gateway_manager init",
            "app enable net_eng",
        ]


    def __getattr__(self, name):
        if name in self.config:
            return self.config[name]

        raise AttributeError

    def is_loaded(self):
        return self.loaded

    def get_platform(self):
        if os.path.isfile("/etc/ttversion"):
            with open("/etc/ttversion") as f:
                lines = f.readlines()
            for line in lines:
                if line[:len("BOARD")] == "BOARD":
                    board = line.split("=")[1].strip("\n")
                    if board == "heimdall_boardv1":
                        return "heimdall_v1"
                    if board == "heimdall_boardv2":
                        return "heimdall_v2"
                    if board == "cm_boardv1":
                        return "cm_v1"
                    if board == "cm_boardv2":
                        return "cm_v2"
                    break
        return "desktop"

    def config_file_exists(self):
        if not os.path.isdir(self.TT_DIR):
            return False
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return False
        return True

    def create_default_config(self):
        self.gateway.platform = self.get_platform()
        os.makedirs(self.TT_DIR, exist_ok=True)
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

    def create_backup_config(self):
        backups_dir = f"{config.TT_DIR}/.backups/config"
        os.makedirs(backups_dir, exist_ok=True)
        now = dt.now().strftime("%Y%m%d-%H%M%S")
        os.system(f"cp {config.TT_DIR}/gw.config "
            + f"{backups_dir}/{now}_gw.config")

    def gwrc_file_exists(self):
        return os.path.isfile(self.GWRC_FILE)

    def create_default_gwrc(self):
        os.makedirs(self.TT_DIR, exist_ok=True)
        with open(self.GWRC_FILE, "w") as f:
            f.write("\n".join(self.default_gwrc) + "\n")

    def create_default_negwrc(self):
        os.makedirs(self.TT_DIR, exist_ok=True)
        with open(self.GWRC_FILE, "w") as f:
            f.write("\n".join(self.default_negwrc) + "\n")

    def create_default_hostname(self):
# pylint: disable=no-member
        if (self.config.gateway.platform.startswith("heimdall")
                and not os.path.exists(self.HOSTNAME_FILE)):
            company = self.config.backend.company
            device_id = self.config.backend.device_id
            with open(self.HOSTNAME_FILE, "w") as f:
                f.write(f"{company}_{device_id}\n")
            os.system("/etc/init.d/hostname.sh")
# pylint: enable=no-member

    def fix_urls(self):
        for key in self.config.keys():
            if "url" in self.config[key]:
                self.config[key]["url"] = self.config[key]["url"].strip("/")

    def _set_config(self, dest, orig):
        for key, o in orig.items():
            if (key in dest and isinstance(o, dict) and
                    isinstance(dest[key], dict)):
                self._set_config(dest[key], o)
            else:
                dest[key] = o

    def read(self):
        try:
            os.makedirs(self.TT_DIR, exist_ok=True)
            with open(self.CONFIG_FILE, 'r') as f:
                self._set_config(self.config, json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            pass
        self.loaded = True
        self.fix_urls()

    def write(self):
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)


config = Config()
if "TTGATEWAY2" in os.environ:
# pylint: disable=invalid-name
    config.TT_DIR = os.path.expanduser("~/.tychetools2")
    config.CONFIG_FILE = f"{config.TT_DIR}/gw.config"
    config.DAEMON_PID_FILE = "/tmp/ttgw.pid2"
    config.SERVER_SOCKET = "/tmp/ttgw.socket2"
# pylint: enable=invalid-name
