import os
import json

from ttgateway.config import config
from ttgateway.cli_client import CLIClient
from ttgateway.remote_cli_client import RemoteCliClient
import ttgateway.commands as cmds

class Diagnosis():
    def __init__(self):
        if os.path.exists(config.DAEMON_PID_FILE):
            self.cli = CLIClient()
        else:
            self.cli = RemoteCliClient()
            self.cli.select_device()

    def run(self):
        diagnosis = {}
        # Gateway check
        gw_check_cmd = cmds.GatewayCheck()
        self.cli.send_cmd(gw_check_cmd)
        gw_check_rsp = self.cli.recv_data(silent=True)
        diagnosis["gw_check"] = gw_check_rsp
        # Config
        diagnosis["config"] = self.config_get()
        # Fault status
        fault_status_cmd = cmds.FaultStatus()
        self.cli.send_cmd(fault_status_cmd)
        fault_status_rsp = self.cli.recv_data(silent=True)
        diagnosis["fault_status"] = fault_status_rsp
        # Node summary
        node_summary_cmd = cmds.NodeSummary()
        self.cli.send_cmd(node_summary_cmd)
        node_summary_rsp = self.cli.recv_data(silent=True)
        if node_summary_rsp:
            diagnosis["node_summary"] = node_summary_rsp["node_summary"]
        else:
            diagnosis["node_summary"] = {}
        # Node list
        node_list_cmd = cmds.NodeList(tel=True, co2=True, iaq=True,
            bat=True, ota=True, pwmt=True, stats=True, tasks=True)
        self.cli.send_cmd(node_list_cmd)
        node_list_rsp = self.cli.recv_data(silent=True)
        if node_list_rsp:
            diagnosis["node_list"] = node_list_rsp["node_list"]
        else:
            diagnosis["node_list"] = []
        # Virtual node list
        virtual_node_list_cmd = cmds.VirtualListNodes()
        self.cli.send_cmd(virtual_node_list_cmd)
        virtual_node_list_rsp = self.cli.recv_data(silent=True)
        if virtual_node_list_rsp:
            diagnosis["virtual_node_list"] = virtual_node_list_rsp["node_list"]
        else:
            diagnosis["virtual_node_list"] = []
        # Return diagnosis
        rsp = json.dumps(diagnosis, indent=4)
        print(rsp)

    def config_get(self):
        config_fields = {
            "gateway": [
                "datetime_period",
                "battery_period",
                "telemetry_period",
                "co2_period",
                "pwmt_period",
                "sleep_time",
                "ping_period",
                "platform",
                "node_db",
                "task_config"
            ],
            "backend": [
                "url",
                "device_id",
                "user",
                "tel_period",
                "bat_period",
                "pwmt_period"
            ],
            "mqtt": [
                "ip",
                "port",
                "prefix"
            ],
            "fault_manager": [
                "transport"
            ],
            "remote_client": [
                "url"
            ],
            "remote_client_cli": [
                "url"
            ],
            "http_logging": [
                "url",
                "period"
            ]
        }
        config_data = {}
        for module, fields in config_fields.items():
            if module not in config_data:
                config_data[module] = {}
            for field in fields:
                self.cli.send_cmd(cmds.ConfigGet(module, field))
                result = self.cli.recv_data(silent=True)
                if not result or "value" not in result:
                    config_data[module][field] = None
                    continue
                config_data[module][field] = result["value"]
        return config_data
