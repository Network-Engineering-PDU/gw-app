import json
import string
import socket
import argparse
import logging
from datetime import datetime as dt
from datetime import timedelta

from cmd2 import Cmd, with_argparser, style, ansi

import ttgateway.commands as cmds
from ttgateway.config import config
from ttgateway.utils import delta_to_timestr
from ttgateway.virtual.virtual_node import VirtualNode

TT_COLOR_MAIN = ansi.Fg.CYAN
TT_COLOR_ERROR = ansi.Fg.RED
TT_COLOR_WARNING = ansi.Fg.YELLOW
TT_COLOR_OK = ansi.Fg.GREEN
TT_INTRO = f"""
Welcome to the {
    style("TycheTools Gateway shell", fg=TT_COLOR_MAIN)
}. Type help to list commands.
"""
TT_PROMPT = style("#gateway> ", fg=TT_COLOR_MAIN, bold=True)


def macaddr(s):
    """ Helper function to define argparse Mac type."""
    if len(s) == 12 and all(c in string.hexdigits for c in s):
        return s
    raise argparse.ArgumentTypeError(f"Invalid MAC address {s}")


def error_style(s: str):
    return style(s, fg=TT_COLOR_ERROR)


def warning_style(s: str):
    return style(s, fg=TT_COLOR_WARNING)


def ok_style(s: str):
    return style(s, fg=TT_COLOR_OK)


def format_val(v, f, l):
    if isinstance(v, str) and "N/A" in v:
        return " " * (l - 3) + v # 3 is the length of "N/A"
    return f.format(v)

def round_float(value, width):
    if isinstance(value, float):
        value = round(value)
    return format_val(value, f'{{:>{width}}}', width)

class CLIClient(Cmd):
    """ TycheTools Gateway CLI Client."""
    intro = TT_INTRO
    prompt = TT_PROMPT
    def __init__(self, *args, startup=False, **kwargs):
        self.startup = startup
        self.socket = None
        super().__init__(*args, **kwargs)

    def do_quit(self, line):
        """Stop Exit."""
        return True

    do_exit = do_quit
    do_q = do_quit
    delattr(Cmd, "do_shell")

    def default(self, statement):
        self.poutput(error_style("Unknown command"))
        return False

    def recv_data(self, silent=False):
        data = bytearray()
        raw_data = self.socket.recv(1024)
        if not raw_data:
            if not silent:
                self.poutput(error_style("Server ended connection"))
            self.do_quit("")

        data_length = int.from_bytes(raw_data[0:4], "little")
        data += raw_data[4:]
        while len(data) < data_length:
            raw_data = self.socket.recv(1024)
            if not raw_data:
                if not silent:
                    self.poutput(error_style("Server ended connection"))
                self.do_quit("")
            data += raw_data

        resp = json.loads(data.decode())
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

    def send_cmd(self, command: cmds.Command):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.connect(config.SERVER_SOCKET)
        self.socket.sendall(command.serialize())

    # ------------------- GATEWAY MANAGER COMMANDS ---------------------
    gateway_manager_parser = argparse.ArgumentParser()
    gateway_manager_sub = gateway_manager_parser.add_subparsers(
        title="subcommands", help="subcommand help")

    gw_mngr_init_parser = gateway_manager_sub.add_parser("init",
        help="init help")
    def gw_mngr_init(self, opts):
        """ Start gateway manager. """
        cmd = cmds.GatewayMngrInit()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    gw_mngr_list_parser = gateway_manager_sub.add_parser("list",
        help="list help")
    def gw_mngr_list(self, opts):
        """ List gateways managed by the gateway manager. """
        cmd = cmds.GatewayMngrList()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        resp = self.recv_data()
        if not resp or not "data" in resp:
            return False
        data = resp["data"]
        gw_mngr_prompt = f"Role: {data['role']}\n"
        gw_mngr_prompt += f"Remote host: {data['remote_host']}\n"
        gw_mngr_prompt += f"Remote port: {data['server_port']}\n"
        gw_mngr_prompt += f"Remote ping period: {data['remote_ping_period']}\n"
        gw_mngr_prompt += f"Active gateways: {data['active_gw']}\n"
        gw_mngr_prompt += f"ID count: {data['id_count']}\n"
        gw_mngr_prompt += f"Local gateways: {len(data['gw_local'])}\n"
        for gw_local in data['gw_local']:
            gw_mngr_prompt += f"\tGateway {gw_local['id']}:\n"
            gw_mngr_prompt += f"\t\tPort: {gw_local['port']}\n"
            last_ping = self.get_last_msg(gw_local['ping_last_ts'])
            gw_mngr_prompt += f"\t\tLast ping: {last_ping}\n"
            gw_mngr_prompt += f"\t\tWhitelist: {gw_local['whitelist']}\n"
        gw_mngr_prompt += f"Remote gateways: {len(data['gw_remote'])}\n"
        for gw_remote in data['gw_remote']:
            gw_mngr_prompt += f"\tGateway {gw_remote['id']}:\n"
            gw_mngr_prompt += f"\t\tHost: {gw_remote['host']}\n"
            gw_mngr_prompt += f"\t\tPort: {gw_remote['port']}\n"
            gw_mngr_prompt += f"\t\tPlatform: {gw_remote['platform']}\n"
            last_ping = self.get_last_msg(gw_remote['ping_last_ts'])
            gw_mngr_prompt += f"\t\tLast ping: {last_ping}\n"
            gw_mngr_prompt += f"\t\tWhitelist: {gw_remote['whitelist']}\n"
        self.poutput(gw_mngr_prompt)
        return False

    gw_mngr_uninit_parser = gateway_manager_sub.add_parser("uninit",
        help="uninit help")
    def gw_mngr_uninit(self, opts):
        """ Uninit gateway manager. """
        cmd = cmds.GatewayMngrUninit()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    gw_mngr_start_scan_parser = gateway_manager_sub.add_parser("start_scan",
        help="start_scan help")
    gw_mngr_start_scan_parser.add_argument("-t", "--timeout", type=int,
        nargs="?", help="scan timeout, in seconds", default=0)
    gw_mngr_start_scan_parser.add_argument("-o", "--one", action="store_true",
        help="Provision only one node")
    gw_mngr_start_scan_parser.add_argument("-g", "--gateway", type=str,
        help="Gateway ID of the target gateway")
    def gw_mngr_start_scan(self, opts):
        """ Start scanning for unprovisioned nodes. If a timeout is
        provided, the scan will stop automatically after the specified
        time.
        """
        cmd = cmds.GatewayStartScan(opts.timeout, opts.one, opts.gateway)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    gw_mngr_stop_scan_parser = gateway_manager_sub.add_parser("stop_scan",
        help="stop_scan help")
    gw_mngr_stop_scan_parser.add_argument("-g", "--gateway", type=str,
        help="Gateway ID of the target gateway")
    def gw_mngr_stop_scan(self, opts):
        """ Stop scanning.
        """
        cmd = cmds.GatewayStopScan(opts.gateway)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    gw_mngr_status_parser = gateway_manager_sub.add_parser("status",
        help="status help")
    gw_mngr_status_parser.add_argument("-g", "--gateway", type=str,
        help="Gateway ID of the target gateway")
    def gw_mngr_status(self, opts):
        """ Return the current gateway status. This includes the
        version, if is listener, if is scanning and provisioning, and the number
        of nodes.
        """
        cmd = cmds.GatewayStatus(opts.gateway)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False
        self.poutput("App version: {}".format(data["app_version"]))
        self.poutput("Lib version: {}".format(data["lib_version"]))
        self.poutput("FW version: {}".format(data["fw_version"]))
        self.poutput("GW Address: 0x{:04X}".format(data["unicast_addr"]))
        self.poutput("Netkey: {}".format(data["netkey"]))
        self.poutput("Nodes: {}/{}".format(data["nodes"], data["max_nodes"]))
        listener = ok_style("yes") if data["listener"] else error_style("no")
        self.poutput("Listener: {}".format(listener))
        scan = ok_style("yes") if data["scanning"] else error_style("no")
        self.poutput("Scanning: {}".format(scan))
        prov = ok_style("yes") if data["provisioning"] else error_style("no")
        self.poutput("Provisioning: {}".format(prov))
        return False

    gw_mngr_sleep_time_parser = gateway_manager_sub.add_parser("sleep_time",
        help="sleep_time help")
    gw_mngr_sleep_time_parser.add_argument("-s", "--set", type=int, nargs=1,
        help="set new default sleep time, in seconds")
    gw_mngr_sleep_time_parser.add_argument("-g", "--gateway", type=str,
        help="Gateway ID of the target gateway")
    def gw_mngr_sleep_time(self, opts):
        """Gets/sets the default sleep time. If called without any
        arguments, prints the current sleep time. Can be called before
        gateway init.
        """
        if opts.set:
            cmd = cmds.GatewaySetSleep(opts.set[0], opts.gateway)
        else:
            cmd = cmds.GatewayGetSleep(opts.gateway)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False
        for k,v in data.items():
            n = " ".join(k.split("_"))
            self.poutput(f"{n}: {v} seconds")
        return False

    gw_mngr_ping_parser = gateway_manager_sub.add_parser("ping",
        help="ping help")
    gw_mngr_ping_parser.add_argument("-g", "--gateway", type=str,
        help="Gateway ID of the target gateway")
    def gw_mngr_ping(self, opts):
        """ Ping the gateway.
        """
        cmd = cmds.GatewayCheck(opts.gateway)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            if data["connection_alive"]:
                self.poutput(ok_style("Ping OK"))
            else:
                self.poutput(error_style("Ping failed"))
        return False

    gw_mngr_listener_parser = gateway_manager_sub.add_parser("listener",
        help="listener help")
    gw_mngr_listener_parser.add_argument("action",
        choices=["enable", "disable"])
    gw_mngr_listener_parser.add_argument("-g", "--gateway", type=str,
        help="Gateway ID of the target gateway")
    def gw_mngr_listener(self, opts):
        """ Enables/disables the listener mode.
        """
        cmd = cmds.GatewayListener(opts.action=="enable", opts.gateway)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    gw_mngr_init_parser.set_defaults(func=gw_mngr_init)
    gw_mngr_uninit_parser.set_defaults(func=gw_mngr_uninit)
    gw_mngr_list_parser.set_defaults(func=gw_mngr_list)
    gw_mngr_start_scan_parser.set_defaults(func=gw_mngr_start_scan)
    gw_mngr_stop_scan_parser.set_defaults(func=gw_mngr_stop_scan)
    gw_mngr_status_parser.set_defaults(func=gw_mngr_status)
    gw_mngr_sleep_time_parser.set_defaults(func=gw_mngr_sleep_time)
    gw_mngr_ping_parser.set_defaults(func=gw_mngr_ping)
    gw_mngr_listener_parser.set_defaults(func=gw_mngr_listener)
    gw_mngr_init_parser.description = gw_mngr_init.__doc__
    gw_mngr_list_parser.description = gw_mngr_list.__doc__
    gw_mngr_start_scan_parser.description = gw_mngr_start_scan.__doc__
    gw_mngr_stop_scan_parser.description = gw_mngr_stop_scan.__doc__
    gw_mngr_status_parser.description = gw_mngr_status.__doc__
    gw_mngr_sleep_time_parser.description = gw_mngr_sleep_time.__doc__
    gw_mngr_ping_parser.description = gw_mngr_ping.__doc__
    gw_mngr_listener_parser.description = gw_mngr_listener.__doc__
    @with_argparser(gateway_manager_parser)
    def do_gateway_manager(self, opts):
        """ gateway manager command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("gateway_manager")


    # --------------- NODE COMMANDS ---------------
    node_parser = argparse.ArgumentParser()
    node_sub = node_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    node_list_parser = node_sub.add_parser("list", help="list help")
    node_list_parser.add_argument("-v", "--verbose", action="store_true",
        help="Verbose output")
    node_list_parser.add_argument("-t", "--telemetry", action="store_true",
        help="Last telemetry data")
    node_list_parser.add_argument("-c", "--co2", action="store_true",
        help="Last CO2 data")
    node_list_parser.add_argument("-i", "--iaq", action="store_true",
        help="Last IAQ data")
    node_list_parser.add_argument("-b", "--battery", action="store_true",
        help="Last battery data")
    node_list_parser.add_argument("-o", "--ota", action="store_true",
        help="OTA status")
    node_list_parser.add_argument("-p", "--pwmt", action="store_true",
        help="Last power meter data")
    node_list_parser.add_argument("-s", "--stats", action="store_true",
        help="Node statistics")
    node_list_parser.add_argument("-k", "--tasks", action="store_true",
        help="Node tasks")
    node_list_parser.add_argument("-g", "--cvg", action="store_true",
        help="Node coverage")
    node_list_parser.add_argument("--table", action="store_true",
        help="Table format output")
    node_list_parser.add_argument("-n", "--nodes", type=macaddr, nargs="+",
        help="MAC address of nodes to list")
    node_list_parser.add_argument("-l", "--last", type=int,
        help="Filter nodes by time (in seconds) since last msg received.")
    def node_list(self, opts):
        """ Print nodes belonging to the Bluetooth network. """
        if opts.verbose and opts.table:
            self.poutput(error_style("Select table or verbose"))
            return False
        cmd = cmds.NodeList(opts.telemetry, opts.co2, opts.iaq, opts.battery,
            opts.ota, opts.pwmt, opts.table, opts.nodes, opts.last, opts.stats,
            opts.tasks, opts.cvg)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False
        i = 0
        na_msg = error_style("N/A")
        if opts.table:
            self.poutput(self.node_list_header(opts))
        data["node_list"].sort(key=lambda n: n["addr"])
        for n in data["node_list"]:
            i += 1
            show_data = {}
            if not any((opts.verbose, opts.telemetry, opts.co2, opts.iaq,
                    opts.battery, opts.ota, opts.pwmt, opts.table, opts.stats,
                    opts.tasks, opts.cvg)):
                self.node_list_show_simple(n)
            elif opts.table:
                self.node_list_show_header_table(n)
            else:
                self.node_list_show_header_args(i)
            if opts.verbose:
                self.node_list_show_verbose(n)
            if opts.telemetry:
                temp = n["temperature"]/100.0 if "temperature" in n else na_msg
                show_data["temp"] = temp
                show_data["humd"] = n["humidity"] if "humidity" in n else na_msg
                pressure = n["pressure"]/10_000.0 if "pressure" in n else na_msg
                show_data["pres"] = pressure
                show_data["rssi"] = n["rssi"] if "rssi" in n else na_msg
            if opts.pwmt:
                metrics = ["v", "i", "p", "q", "s", "pf", "ph", "f", "e"]
                total_metrics = ["total_p", "total_q", "total_s","total_e"]
                for m in metrics:
                    show_data[f"{m}1"] = na_msg
                    show_data[f"{m}2"] = na_msg
                    show_data[f"{m}3"] = na_msg
                for tm in total_metrics:
                    show_data[tm] = na_msg
                if "lines" in n:
                    for line in n["lines"]:
                        if line["line_id"] in [1, 2, 3]:
                            params = {
                                f"v{line['line_id']}": "voltage",
                                f"i{line['line_id']}": "current",
                                f"p{line['line_id']}": "active_power",
                                f"q{line['line_id']}": "reactive_power",
                                f"s{line['line_id']}": "apparent_power",
                                f"pf{line['line_id']}": "power_factor",
                                f"ph{line['line_id']}": "phase_vi",
                                f"f{line['line_id']}": "frequency",
                                f"e{line['line_id']}": "energy"
                            }
                        else:
                            params = {
                                "total_p": "total_active_power",
                                "total_q": "total_reactive_power",
                                "total_s": "total_apparent_power",
                                "total_e": "total_energy"
                            }
                        for key, value in params.items():
                            if value in line:
                                show_data[key] = line[value]
                            else:
                                show_data[key] = na_msg
            if opts.co2:
                show_data["co2"] = n["co2"] if "co2" in n else na_msg
            if opts.iaq:
                show_data["iaq"] = n["iaq"] if "iaq" in n else na_msg
                show_data["tvoc"] = n["tvoc"] if "tvoc" in n else na_msg
                show_data["etoh"] = n["etoh"] if "etoh" in n else na_msg
                show_data["eco2"] = n["eco2"] if "eco2" in n else na_msg
            if opts.battery:
                battery = n["battery"]/1000.0 if "battery" in n else na_msg
                show_data["battery"] = battery
            if opts.ota:
                show_data["ota_stat"] = n["status"] if "status" in n else na_msg
            if opts.stats:
                rssi_avg = round(n["rssi_avg"],1) if "rssi_avg" in n else na_msg
                show_data["rssi_avg"] = rssi_avg
                show_data["ttl_127"] = n["ttl"][0] if "ttl" in n else na_msg
                show_data["ttl_126"] = n["ttl"][1] if "ttl" in n else na_msg
                show_data["ttl_125"] = n["ttl"][2] if "ttl" in n else na_msg
                show_data["ttl_<124"] = n["ttl"][3] if "ttl" in n else na_msg
                if "last_reset" in n:
                    last_reset = dt.fromtimestamp(n["last_reset"])
                    last_reset_str = last_reset.strftime("%d/%m/%y %H:%M")
                    show_data["last_reset"] = last_reset_str
                else:
                    show_data["last_reset"] = na_msg
            if opts.tasks:
                show_data["configured_tasks"] = na_msg
                if "configured_tasks" in n:
                    show_data["configured_tasks"] = n["configured_tasks"]
            if opts.cvg:
                show_data["coverage"] = na_msg
                if "coverage" in n:
                    show_data["coverage"] = n["coverage"]
            if opts.table:
                self.node_list_show_table(opts, show_data)
            else:
                self.node_list_show(opts, show_data)
        return False

    def node_list_header(self, opts):
        s = " " * 15
        if opts.telemetry:
            s += "|     TEMP | HUMD |       PRES |   RSSI "
        if opts.co2:
            s += "|    CO2 "
        if opts.iaq:
            s += "| IAQ    TVOC    ETOH   eCO2 "
        if opts.battery:
            s += "|    BAT "
        if opts.ota:
            s += "|  OTA "
        if opts.pwmt:
            s += "|    VOLTAGE (V) |    CURRENT (A) "
            s += "|   AVTIVE P (W) | ACTIVE P (VAr) "
            s += "|  APPAR. P (VA) |   POWER FACTOR "
            s += "|    PHASE (deg) | FREQUENCY (Hz) "
            s += "|    ENERGY (Wh) | TOTAL P/Q/S/E"
        if opts.stats:
            s += "| RSSI AVG "
            s += "|  DIRECT |   1 HOP |   2 HOP |  >3 HOP "
            s += "|     LAST RESET "
        if opts.tasks:
            s += "|       TASKS "
        return s

    def get_last_msg(self, last_msg_ts):
        if last_msg_ts:
            msg_timestamp = dt.fromtimestamp(last_msg_ts)
            delta = dt.now() - msg_timestamp
            if delta.days:
                last_msg = msg_timestamp.strftime("%d/%m/%Y")
            else:
                last_msg = delta_to_timestr(delta) + " ago"
        else:
            last_msg = error_style("--:--:--") + " ago"
        return last_msg

    def node_get_next_wake(self, last_wake_ts, sleep_period):
        if last_wake_ts:
            wake_ts = dt.fromtimestamp(last_wake_ts)
            wake_time = wake_ts + timedelta(seconds=sleep_period)
            delta = wake_time - dt.now()
            if delta.days < 0:
                if delta.days != -1:
                    next_wake = error_style(wake_ts.strftime("%d/%m/%Y"))
                else:
                    d1 = dt.now() - wake_ts
                    next_wake = error_style(delta_to_timestr(d1)) + " ago"
            else:
                if delta.days:
                    next_wake = wake_time.strftime("%d/%m/%Y")
                else:
                    next_wake = delta_to_timestr(delta)
        else:
            next_wake = error_style("--:--:--")
        return next_wake

    def node_list_show_simple(self, node):
        last_msg = self.get_last_msg(node["last_msg_ts"])
        next_wake = self.node_get_next_wake(node["last_wake_ts"],
            node["sleep_period"])
        s = f"Node {node['mac']} {'(' + str(node['addr']):>4}) | " + \
            f"board {node['board_id']:<2} | recv {last_msg} | wake {next_wake}"
        self.poutput(s)

    def node_list_show_header_table(self, node):
        s = f"Node {node['addr']:<4} {'(' + str(node['board_id']):>3}) "
        self.poutput(s, end = '')

    def node_list_show_header_args(self, index):
        self.poutput(f"Node {index}:")

    def node_list_show_verbose(self, node):
        last_msg = self.get_last_msg(node["last_msg_ts"])
        next_wake = self.node_get_next_wake(node["last_wake_ts"],
            node["sleep_period"])
        verb_text =  f"\tUnicast Address: {node['addr']}\n\t"
        verb_text += f"MAC: {node['mac']}\n\t"
        verb_text += f"UUID: {node['uuid']}\n\t"
        verb_text += f"Board ID: {node['board_id']}\n\t"
        verb_text += f"Tasks: {node['pending_tasks']}\n\t"
        verb_text += f"Sleep time: {node['sleep_period']} seconds \n\t"
        verb_text += f"Time to wake: {next_wake}\n\t"
        verb_text += f"Last message: {last_msg}"
        self.poutput(verb_text)

    def node_list_show_table(self, opts, show_data):
        if opts.telemetry:
            s  = f"| {format_val(show_data['temp'], '{:6.2f}', 6)}ºC "
            s += f"| {format_val(show_data['humd'], '{:3d}', 3)}% "
            s += f"| {format_val(show_data['pres'], '{:7.2f}', 7)}hPa "
            s += f"| {format_val(show_data['rssi'], '{:+3d}', 3)}dBm "
            self.poutput(s, end = '')
        if opts.co2:
            s =  f"| {format_val(show_data['co2'], '{:3d}', 3)}ppm "
            self.poutput(s, end = '')
        if opts.iaq:
            s  = f"| {format_val(show_data['iaq'], '{:1d}', 1)}, "
            s += f"{format_val(show_data['tvoc'], '{:6.2f}', 6)}, "
            s += f"{format_val(show_data['etoh'], '{:6.2f}', 6)}, "
            s += f"{format_val(show_data['eco2'], '{:4d}', 4)}, "
            self.poutput(s, end = '')
        if opts.battery:
            s = f"| {format_val(show_data['battery'], '{:5.3f}', 5)}V "
            self.poutput(s, end = '')
        if opts.ota:
            s = f"| {format_val(show_data['ota_stat'], '{:4d}', 4)} "
            self.poutput(s, end = '')
        if opts.pwmt:
            s = ""
            metrics = ["v", "i", "p", "q", "s", "pf", "ph", "f", "e"]
            for m in metrics:
                s += f"| {round_float(show_data[f'{m}1'], 4)}"
                s += f" {round_float(show_data[f'{m}2'], 4)}"
                s += f" {round_float(show_data[f'{m}3'], 4)} "
            s += f"| {round_float(show_data['total_p'], 4)}"
            s += f"/{round_float(show_data['total_q'], 4)}"
            s += f"/{round_float(show_data['total_s'], 4)}"
            s += f"/{round_float(show_data['total_e'], 4)}"
            self.poutput(s, end = '')
        if opts.stats:
            s  = f"| {format_val(show_data['rssi_avg'], '{:.1f}', 5)}dBm "
            s += f"| {format_val(show_data['ttl_127'], '{:7d}', 7)} "
            s += f"| {format_val(show_data['ttl_126'], '{:7d}', 7)} "
            s += f"| {format_val(show_data['ttl_125'], '{:7d}', 7)} "
            s += f"| {format_val(show_data['ttl_<124'], '{:7d}', 7)} "
            s += f"| {format_val(show_data['last_reset'], '{:>14}', 14)} "
            self.poutput(s, end = '')
        if opts.tasks:
            s = f"| {show_data['pending_tasks']} "
            self.poutput(s, end = '')
        self.poutput("")

    def node_list_show(self, opts, show_data):
        if opts.telemetry:
            tel_text =  f"\tTemperature: {show_data['temp']}\n\t"
            tel_text += f"Humidity: {show_data['humd']}\n\t"
            tel_text += f"Pressure: {show_data['pres']}\n\t"
            tel_text += f"RSSI: {show_data['rssi']}"
            self.poutput(tel_text)
        if opts.co2:
            co2_text = f"\tCO2: {show_data['co2']}"
            self.poutput(co2_text)
        if opts.iaq:
            iaq_text =  f"\tIAQ: {show_data['iaq']}\n\t"
            iaq_text += f"TVOC: {show_data['tvoc']}\n\t"
            iaq_text += f"ETOH: {show_data['etoh']}\n\t"
            iaq_text += f"ECO2: {show_data['eco2']}"
            self.poutput(iaq_text)
        if opts.battery:
            bat_text = f"\tBattery: {show_data['battery']}"
            self.poutput(bat_text)
        if opts.ota:
            ota_text = f"\tOTA status: {show_data['ota_stat']}"
            self.poutput(ota_text)
        if opts.pwmt:
            pwmt_text = "\t"
            metrics = ["v", "i", "p", "q", "s", "pf", "ph", "f", "e"]
            metrics_name = ["Voltage (V)", "Current (A)", "Active power (W)", \
                "Reactive power (VAr)", "Apparent power (VA)", "Power factor", \
                "Phase (deg)", "Frequency (Hz)", "Energy (Wh)"]
            for i, m in enumerate(metrics):
                pwmt_text += f"{metrics_name[i]}: {show_data[f'{m}1']} / " \
                    f"{show_data[f'{m}2']} / {show_data[f'{m}3']}\n\t"
            pwmt_text = pwmt_text[:-2] # To avoid carriage return on last line
            self.poutput(pwmt_text)
        if opts.stats:
            stats_text  = f"\tRSSI avg: {show_data['rssi_avg']}\n\t"
            stats_text += f"Direct packets: {show_data['ttl_127']}\n\t"
            stats_text += f"1 hop packets:  {show_data['ttl_126']}\n\t"
            stats_text += f"2 hops packets: {show_data['ttl_125']}\n\t"
            stats_text += f"3 or more hops: {show_data['ttl_<124']}\n\t"
            stats_text += f"Last reset: {show_data['last_reset']}"
            self.poutput(stats_text)
        if opts.tasks:
            tasks_text = f"\tConfigured tasks: {show_data['configured_tasks']}"
            self.poutput(tasks_text)
        if opts.cvg:
            cvg_text = "\tGateway coverage: "
            if isinstance(show_data["coverage"], str):
                cvg_text += show_data["coverage"]
            else:
                cvg_text += "\n\t\t"
                for gateway, cvg in show_data["coverage"].items():
                    cvg_text += f"Gateway {gateway}: "
                    ts = cvg['timestamp']
                    rssi = cvg['rssi']
                    assigned = cvg['assigned']
                    cvg_text += f"({ts}, {rssi}, {assigned})\n\t\t"
            self.poutput(cvg_text)

    node_summary_parser = node_sub.add_parser("summary", help="summary help")
    def node_summary(self, opts):
        """ Prints a summary of the nodes belonging the Bluetooth Network.
        """
        cmd = cmds.NodeSummary()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()["node_summary"]
        na_msg = error_style("N/A")
        per_drct = data['per_drct'] if data['per_drct'] is not None else na_msg
        per_1hop = data['per_1hop'] if data['per_1hop'] is not None else na_msg
        per_2hop = data['per_2hop'] if data['per_2hop'] is not None else na_msg
        per_3hop = data['per_3hop'] if data['per_3hop'] is not None else na_msg
        batt_avg = data['batt_avg'] if data['batt_avg'] else na_msg
        batt_min = data['batt_min'] if data['batt_min'] else na_msg
        batt_max = data['batt_max'] if data['batt_max'] else na_msg
        rssi_avg = data['rssi_avg'] if data['rssi_avg'] else na_msg
        rssi_min = data['rssi_min'] if data['rssi_min'] else na_msg
        rssi_max = data['rssi_max'] if data['rssi_max'] else na_msg
        temp_avg = data['temp_avg'] if data['temp_avg'] else na_msg
        temp_min = data['temp_min'] if data['temp_min'] else na_msg
        temp_max = data['temp_max'] if data['temp_max'] else na_msg
        humd_avg = data['humd_avg'] if data['humd_avg'] else na_msg
        humd_min = data['humd_min'] if data['humd_min'] else na_msg
        humd_max = data['humd_max'] if data['humd_max'] else na_msg
        pres_avg = data['pres_avg'] if data['pres_avg'] else na_msg
        pres_min = data['pres_min'] if data['pres_min'] else na_msg
        pres_max = data['pres_max'] if data['pres_max'] else na_msg
        summ = ""
        summ += f"Total number of nodes: {data['nodes_number']}\n"
        summ += f"Active nodes (1h ago): {data['nodes_active']}\n"
        summ += f"Percentage of active nodes: {data['perct_active']} %\n"
        summ += f"Direct packets: {data['msg_drct']} ({per_drct} %)\n"
        summ += f"1 hops packets: {data['msg_1hop']} ({per_1hop} %)\n"
        summ += f"2 hops packets: {data['msg_2hop']} ({per_2hop} %)\n"
        summ += f"3 or more hops: {data['msg_3hop']} ({per_3hop} %)\n"
        summ += f"Battery average: {batt_avg} V\n"
        summ += f"Battery minimum: {batt_min} V\n"
        summ += f"Battery maximum: {batt_max} V\n"
        summ += f"RSSI average: {rssi_avg} dBm\n"
        summ += f"Average RSSI minimum: {rssi_min} dBm\n"
        summ += f"Average RSSI maximum: {rssi_max} dBm\n"
        summ += f"Temperature average: {temp_avg} ºC\n"
        summ += f"Temperature minimum: {temp_min} ºC\n"
        summ += f"Temperature maximum: {temp_max} ºC\n"
        summ += f"Humidity average: {humd_avg} %HR\n"
        summ += f"Humidity minimum: {humd_min} %HR\n"
        summ += f"Humidity maximum: {humd_max} %HR\n"
        summ += f"Pressure average: {pres_avg} hPa\n"
        summ += f"Pressure minimum: {pres_min} hPa\n"
        summ += f"Pressure maximum: {pres_max} hPa"
        self.poutput(summ)
        return False

    node_cancel_tasks_parser = node_sub.add_parser("cancel_tasks",
        help="cancel_tasks help")
    node_cancel_tasks_parser.add_argument("MACADDR", type=macaddr, nargs="+",
        help="MAC address of node to reset")
    def node_cancel_tasks(self, opts):
        """ Cancel all tasks of the given nodes. A node is selected by
        its mac, which should be a 12 letter string.
        """
        cmd = cmds.NodeCancelTasks(opts.MACADDR)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_reset_parser = node_sub.add_parser("reset", help="reset help")
    node_reset_parser.add_argument("MACADDR", type=macaddr, nargs="+",
        help="MAC address of node to reset")
    def node_reset(self, opts):
        """ Reset the given nodes. A node is selected by its mac,
        which should be a 12 letter string.
        """
        cmd = cmds.NodeReset(opts.MACADDR)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_rate_parser = node_sub.add_parser("rate", help="rate help")
    node_rate_parser.add_argument("RATE" , type=int, nargs=1,
        help="new sampling rate, in seconds")
    node_rate_parser.add_argument("MACADDR", type=macaddr, nargs="+",
        help="MAC address of nodes to configure")
    def node_rate(self, opts):
        """Changes the sampling rate of the given nodes. A node is
        selected by its mac, which should be a 12 letter string.
        """
        cmd = cmds.NodeRate(opts.RATE[0], opts.MACADDR)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_rssi_start_parser = node_sub.add_parser("rssi_start",
        help="rssi_start help")
    node_rssi_start_parser.add_argument("datetime", type=str, nargs=1,
        help="Datetime to be scheduled: \"dd/mm/yyyy HH:MM:SS\" ")
    def node_rssi_start(self, opts):
        """Schedules a new rssi sending task at the given datetime.
        """
        cmd = cmds.NodeRssiStart(opts.datetime[0])
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_rssi_get_parser = node_sub.add_parser("rssi_get", help="rssi_get help")
    node_rssi_get_parser.add_argument("-n", "--nodes", type=macaddr, nargs="+",
        help="MAC address of nodes to schedule")
    def node_rssi_get(self, opts):
        """Get rssi table for the requested nodes. If called without any
        arguments, requests every provisioned node table. A node is
        selected by its mac, which should be a 12 letter string.
        """
        cmd = cmds.NodeRssiGet(opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_rssi_ping_parser = node_sub.add_parser("ping", help="ping help")
    node_rssi_ping_parser.add_argument("MACADDR", type=macaddr, nargs="+",
        help="MAC address of node/s to ping")
    def node_rssi_ping(self, opts):
        """Send ping to the given node/s. A node is selected by its mac,
        which should be a 12 letter string.
        """
        cmd = cmds.NodeRssiPing(opts.MACADDR)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_accel_off_parser = node_sub.add_parser("accel_off",
        help="accel_off help")
    def node_accel_off(self, opts):
        """ Set accel off for every node.
        """
        cmd = cmds.NodeAccelOff()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_ota_parser = node_sub.add_parser("ota",
        help="ota help")
    node_ota_parser.add_argument("ota_file", type=str,
        help="Zip file with OTA information and firmware")
    node_ota_parser.add_argument("datetime", type=str,
        help="Datetime to be scheduled: \"dd/mm/yyyy HH:MM:SS\"")
    node_ota_parser.add_argument("ota_type", type=str,
        help="OTA type: (app, sd, bl)")
    node_ota_parser.add_argument("-n", "--nodes", type=macaddr, nargs="+",
        help="MAC address of nodes to schedule")
    def node_ota(self, opts):
        """Schedules an ota update at the given datetime for given nodes. If
        called without specifying a list of nodes, the update is still sent at
        the scheduled time.
        """
        cmd = cmds.NodeOta(opts.ota_file, opts.datetime, opts.ota_type,
            opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_task_create_parser = node_sub.add_parser("task_create",
        help="task_create help")
    node_task_create_parser.add_argument("opcode", type=int,
        help="Existing opcode for the new task")
    node_task_create_parser.add_argument("-d", "--datetime", type=str,
        help="Date and time to be scheduled: \"dd/mm/yyyy HH:MM:SS\"." +
        "Default as soon as possible")
    node_task_create_parser.add_argument("-i", "--period", type=int,
        help="Period (interval) in seconds of the task to be scheduled. " +
        "Default non-periodic")
    node_task_create_parser.add_argument("-c", "--clock", type=str,
        choices=("real", "monotonic"), help="Clock type. Default real")
    node_task_create_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule. Default every node")
    def node_task_create(self, opts):
        """Schedules a task at the given datetime with the given period for
        given nodes.
        """
        clock = 1 if opts.clock == "real" else 0
        cmd = cmds.NodeTaskCreate(opts.opcode, opts.datetime, opts.period,
            clock, opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_task_delete_parser = node_sub.add_parser("task_delete",
        help="task_delete help")
    node_task_delete_parser.add_argument("opcode", type=int,
        help="Existing opcode for the new task")
    node_task_delete_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule")
    def node_task_delete(self, opts):
        """Deletes a scehduled task by OP for the given nodes.
        """
        cmd = cmds.NodeTaskDelete(opts.opcode, opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_task_modify_parser = node_sub.add_parser("task_modify",
        help="task_delete help")
    node_task_modify_parser.add_argument("opcode", type=int,
        help="Existing opcode for the new task")
    node_task_modify_parser.add_argument("-d", "--datetime", type=str,
        help="Date and time to be scheduled: \"dd/mm/yyyy HH:MM:SS\"." +
        "Default as soon as possible")
    node_task_modify_parser.add_argument("-i", "--period", type=int,
        help="Period (interval) in seconds of the task to be scheduled. " +
        "Default non-periodic")
    node_task_modify_parser.add_argument("-c", "--clock", type=str,
        choices=("real", "monotonic"), help="Clock type. Default real")
    node_task_modify_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule. Default every node")
    def node_task_modify(self, opts):
        """Modifies the datetime and period of a scehduled task by OP for the
        given nodes. If the task does not exist, it creates a new task.
        """
        clock = 1 if opts.clock == "real" else 0
        cmd = cmds.NodeTaskModify(opts.opcode, opts.datetime, opts.period,
            clock, opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_tasks_get_parser = node_sub.add_parser("tasks_get",
        help="task_delete help")
    node_tasks_get_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule")
    def node_tasks_get(self, opts):
        """Gets the node scheduled tasks for the given nodes.
        """
        cmd = cmds.NodeTasksGet(opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_ota_status_parser = node_sub.add_parser("ota_status",
        help="status help")
    node_ota_status_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes")
    def node_ota_status(self, opts):
        """ Current OTA status. If called without specifying a list of nodes,
        the command is sent to all nodes.
        """
        cmd = cmds.NodeOtaStatus(opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_beacon_start_parser = node_sub.add_parser("beacon_start",
        help="beacon_stop help")
    node_beacon_start_parser.add_argument("PERIOD" , type=int, nargs=1,
        help="beacon packet period, in milliseconds")
    node_beacon_start_parser.add_argument("MACADDR", type=macaddr, nargs="+",
        help="MAC address of nodes")
    def node_beacon_start(self, opts):
        """ Start node BLE beacon.
        """
        cmd = cmds.NodeBeaconStart(opts.PERIOD[0], opts.MACADDR)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_beacon_stop_parser = node_sub.add_parser("beacon_stop",
        help="beacon_stop help")
    node_beacon_stop_parser.add_argument("MACADDR", type=macaddr, nargs="+",
        help="MAC address of nodes")
    def node_beacon_stop(self, opts):
        """ Stop node BLE beacon.
        """
        cmd = cmds.NodeBeaconStop(opts.MACADDR)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_set_pwmt_conf_parser = node_sub.add_parser("set_pwmt_conf",
        help="set_pwmt_conf help")
    node_set_pwmt_conf_parser.add_argument("phases", type=int,
        help="Phases to receive (TOT|L1|L2|L3)")
    node_set_pwmt_conf_parser.add_argument("stats", type=int,
        help="Stats to receive (avg|max|min)")
    node_set_pwmt_conf_parser.add_argument("values_ph", type=int,
        help="Phase values to receive (VIF|Ppf|QSph|E)")
    node_set_pwmt_conf_parser.add_argument("values_tot", type=int,
        help="Total values to receive (PQS|phph|vph|E)")
    node_set_pwmt_conf_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule")
    def node_set_pwmt_conf(self, opts):
        """ Set pwmt configuration.
        """
        cmd = cmds.NodeSetPwmtConfig(opts.phases, opts.stats, opts.values_ph,
                opts.values_tot, opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_set_pwmt_conv_parser = node_sub.add_parser("set_pwmt_conv",
        help="set_pwmt_conv help")
    node_set_pwmt_conv_parser.add_argument("kv", type=float,
        help="New votage conversion factor")
    node_set_pwmt_conv_parser.add_argument("ki", type=float,
        help="New current conversion factor")
    node_set_pwmt_conv_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule")
    def node_set_pwmt_conv(self, opts):
        """ Set the pwmt channels conversion factor.
            28 bit, sended (int)(k * 1000)
            Max kv, ki = 268435,455
        """
        cmd = cmds.NodeSetPwmtConv(opts.kv * 1000, opts.ki * 1000, opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_temp_mode_parser = node_sub.add_parser("temp_mode",
        help="temp_mode help")
    node_temp_mode_parser.add_argument("mode", type=int,
        help="Temperature/Humidity sensor mode.")
    node_temp_mode_parser.add_argument("-n", "--nodes", type=macaddr,
        nargs="+", help="MAC address of nodes to schedule")
    def node_temp_mode(self, opts):
        """ Calibrate temperature, humidity and pressure for the given node.
        """
        cmd = cmds.NodeTempMode(opts.mode, opts.nodes)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_calibrate_parser = node_sub.add_parser("calibrate",
        help="calibrate help")
    node_calibrate_parser.add_argument("node", type=macaddr,
        help="MAC address of the node to calibrate")
    node_calibrate_parser.add_argument("temperature", type=float,
        help="Temperature offset (ºC)")
    node_calibrate_parser.add_argument("humidity", type=int,
        help="Humidity offset (%%HR)")
    node_calibrate_parser.add_argument("pressure", type=int,
        help="Pressure offset (hPa)")
    def node_calibrate(self, opts):
        """ Calibrate temperature, humidity and pressure for the given node.
        """
        cmd = cmds.NodeCalibrate(opts.temperature, opts.humidity, opts.pressure,
                opts.node)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_reset_calibration_parser = node_sub.add_parser("calibration_reset",
        help="calibration_reset help")
    node_reset_calibration_parser.add_argument("node", type=macaddr,
        help="MAC address of the node to reset calibration")
    node_reset_calibration_parser.add_argument("temperature",
        choices=("True", "False"), help="Temperature")
    node_reset_calibration_parser.add_argument("humidity",
        choices=("True", "False"), help="Humidity")
    node_reset_calibration_parser.add_argument("pressure",
        choices=("True", "False"), help="Pressure")
    def node_reset_calibration(self, opts):
        """ Calibrate temperature, humidity and pressure for the given node.
        """
        temp = opts.temperature == "True"
        humd = opts.humidity == "True"
        press = opts.pressure == "True"
        cmd = cmds.NodeResetCalibration(temp, humd, press, opts.node)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_set_dac_parser = node_sub.add_parser("set_dac",
        help="set_dac help")
    node_set_dac_parser.add_argument("node", type=macaddr,
        help="MAC address of the node to set DAC")
    node_set_dac_parser.add_argument("value", type=float,
        help="DAC value (float, 0-1)")
    def node_set_dac(self, opts):
        """ Sets an output DAC value for the given node.
        """
        cmd = cmds.NodeSetDAC(opts.value, opts.node)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_set_relay_parser = node_sub.add_parser("set_relay",
        help="set_relay help")
    node_set_relay_parser.add_argument("node", type=macaddr,
        help="MAC address of the node to set relay output")
    node_set_relay_parser.add_argument("status", type=int,
        help="Relay output (0/1)")
    def node_set_relay(self, opts):
        """ Sets an relay output for the given node.
        """
        cmd = cmds.NodeSetRelay(opts.status, opts.node)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_set_failsafe_parser = node_sub.add_parser("set_failsafe",
        help="set_failsafe help")
    node_set_failsafe_parser.add_argument("node", type=macaddr,
        help="MAC address of the node to set failsafe output")
    node_set_failsafe_parser.add_argument("relay", type=int,
        help="Relay output (0/1)")
    node_set_failsafe_parser.add_argument("dac", type=float,
        help="DAC value (0-1)")
    def node_set_failsafe(self, opts):
        """ Set failsafe for the given node.
        """
        cmd = cmds.NodeSetFailsafe(opts.relay, opts.dac, opts.node)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_send_out_vector_parser = node_sub.add_parser("send_out_vector",
        help="send_out_vector help")
    node_send_out_vector_parser.add_argument("path", type=str,
        help="Path to the cmd vector JSON file")
    def node_send_out_vector(self, opts):
        """ Set output vector for the given node.
        """
        cmd = cmds.NodeSendOutVector(opts.path)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_output_status_parser = node_sub.add_parser("output_status",
        help="output_status help")
    def node_output_status(self, opts):
        """ Set output vector for the given node.
        """
        cmd = cmds.NodeOutputStatus()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False
        output_status = "\n"
        for node in data["output_status"]:
            output_status += f"Node {node['mac']}:\n"
            output_status += f"\tStatus: {node['status']}\n"
            output_status += f"\tCMD vector: {node['cmd_vector']}\n"
        self.poutput(output_status)
        return False

    node_reboot_parser = node_sub.add_parser("reboot")
    node_reboot_parser.add_argument("node", type=macaddr,
        help="MAC address of the node to reboot")
    def node_reboot(self, opts):
        cmd = cmds.NodeReboot(opts.node)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    node_reboot_parser.set_defaults(func=node_reboot)
    node_list_parser.set_defaults(func=node_list)
    node_cancel_tasks_parser.set_defaults(func=node_cancel_tasks)
    node_reset_parser.set_defaults(func=node_reset)
    node_rate_parser.set_defaults(func=node_rate)
    node_rssi_start_parser.set_defaults(func=node_rssi_start)
    node_rssi_get_parser.set_defaults(func=node_rssi_get)
    node_rssi_ping_parser.set_defaults(func=node_rssi_ping)
    node_accel_off_parser.set_defaults(func=node_accel_off)
    node_ota_parser.set_defaults(func=node_ota)
    node_task_create_parser.set_defaults(func=node_task_create)
    node_task_delete_parser.set_defaults(func=node_task_delete)
    node_task_modify_parser.set_defaults(func=node_task_modify)
    node_tasks_get_parser.set_defaults(func=node_tasks_get)
    node_ota_status_parser.set_defaults(func=node_ota_status)
    node_beacon_start_parser.set_defaults(func=node_beacon_start)
    node_beacon_stop_parser.set_defaults(func=node_beacon_stop)
    node_set_pwmt_conf_parser.set_defaults(func=node_set_pwmt_conf)
    node_set_pwmt_conv_parser.set_defaults(func=node_set_pwmt_conv)
    node_temp_mode_parser.set_defaults(func=node_temp_mode)
    node_calibrate_parser.set_defaults(func=node_calibrate)
    node_reset_calibration_parser.set_defaults(func=node_reset_calibration)
    node_set_dac_parser.set_defaults(func=node_set_dac)
    node_set_relay_parser.set_defaults(func=node_set_relay)
    node_set_failsafe_parser.set_defaults(func=node_set_failsafe)
    node_send_out_vector_parser.set_defaults(func=node_send_out_vector)
    node_output_status_parser.set_defaults(func=node_output_status)
    node_summary_parser.set_defaults(func=node_summary)
    node_list_parser.description = node_list.__doc__
    node_cancel_tasks_parser.description = node_cancel_tasks.__doc__
    node_reset_parser.description = node_reset.__doc__
    node_rate_parser.description = node_rate.__doc__
    node_rssi_start_parser.description = node_rssi_start.__doc__
    node_rssi_get_parser.description = node_rssi_get.__doc__
    node_rssi_ping_parser.description = node_rssi_ping.__doc__
    node_accel_off_parser.description = node_accel_off.__doc__
    node_ota_parser.description = node_ota.__doc__
    node_task_create_parser.description = node_task_create.__doc__
    node_task_delete_parser.description = node_task_delete.__doc__
    node_task_modify_parser.description = node_task_modify.__doc__
    node_tasks_get_parser.description = node_tasks_get.__doc__
    node_ota_status_parser.description = node_ota_status.__doc__
    node_beacon_start_parser.description = node_beacon_start.__doc__
    node_beacon_stop_parser.description = node_beacon_stop.__doc__
    node_set_pwmt_conf_parser.description = node_set_pwmt_conf.__doc__
    node_set_pwmt_conv_parser.description = node_set_pwmt_conv.__doc__
    node_calibrate_parser.description = node_calibrate.__doc__
    node_temp_mode_parser.description = node_temp_mode.__doc__
    node_reset_calibration_parser.description = node_reset_calibration.__doc__
    node_set_dac_parser.description = node_set_dac.__doc__
    node_set_relay_parser.description = node_set_relay.__doc__
    node_set_failsafe_parser.description = node_set_failsafe.__doc__
    node_send_out_vector_parser.description = node_send_out_vector.__doc__
    node_output_status_parser.description = node_output_status.__doc__
    node_summary_parser.description = node_summary.__doc__
    @with_argparser(node_parser)
    def do_node(self, opts):
        """ Node command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("node")


    # ------------------- VIRTUAL NODE COMMANDS ---------------------
    virt_parser = argparse.ArgumentParser()
    virt_sub = virt_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    virt_list_node_parser = virt_sub.add_parser("list_nodes",
            help="list_nodes help")
    virt_list_node_parser.add_argument("-v", "--verbose", action="store_true",
        help="Verbose output")
    def virt_list_nodes(self, opts):
        """ Print virtual nodes. """
        cmd = cmds.VirtualListNodes()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        thr = VirtualNode.BASE_UNICAST_ADDRESS_LOCAL
        local_nodes = [n for n in data["node_list"] if n["address"] >= thr]
        remote_nodes = [n for n in data["node_list"] if n["address"] < thr]
        if local_nodes:
            self.poutput("Local virtual nodes:")
            for node in local_nodes:
                self._virt_print_node(node, opts.verbose)
            if remote_nodes:
                self.poutput()
        if remote_nodes:
            self.poutput("Remote (backend) virtual nodes:")
            for node in remote_nodes:
                self._virt_print_node(node, opts.verbose)
        return False

    def _virt_print_node(self, node, verbose):
        self.poutput("  Virtual node {}".format(node["address"]))
        if verbose:
            self.poutput("    Address: {}".format(node["address"]))
            self.poutput("    MAC: {}".format(node["mac"]))
            self.poutput("    UUID: {}".format(node["uuid"]))
            self.poutput("    Function: {}".format(node["function"]))

    virt_create_node_parser = virt_sub.add_parser("create_node",
            help="create_node help")
    virt_create_node_parser.add_argument("FUNCTION", type=str,
        choices=['maximum', 'minimum', 'median', 'max_no_outliers',
        'min_no_outliers', 'weighted_sum', 'backend_get', 'snmp_get',
        'modbus_get'],
        help="Virtual type")
    virt_create_node_parser.add_argument("ARGS", type=str,
            help="Function arguments (JSON)")
    def virt_create_node(self, opts):
        """ Create new virtual node. """
        cmd = cmds.VirtualCreateNode(opts.FUNCTION, opts.ARGS)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False
        mac = data["node"]["mac"]
        address = data["node"]["address"]
        self.poutput(f"New node {mac} with address {address} created")
        return False

    virt_rm_node_parser = virt_sub.add_parser("remove_node",
            help="remove_node help")
    virt_rm_node_parser.add_argument("NODE_ADDRESS", type=int,
        help="Virtual node address")
    def virt_remove_node(self, opts):
        """ Remove virtual nodes. """
        cmd = cmds.VirtualRemoveNode(opts.NODE_ADDRESS)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    virt_list_funcs_parser = virt_sub.add_parser("list_functions",
            help="list_functions help")
    def virt_list_functions(self, opts):
        """ List functions from virtual nodes. """
        cmd = cmds.VirtualListFunctions()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        self.poutput("Functions:")
        for func in data["function_list"]:
            self.poutput("\t" + func["name"])
            self.poutput("\t\tParams:")
            for param in func["args"]:
                self.poutput("\t\t\t" + param)
        return False

    virt_list_node_parser.set_defaults(func=virt_list_nodes)
    virt_create_node_parser.set_defaults(func=virt_create_node)
    virt_rm_node_parser.set_defaults(func=virt_remove_node)
    virt_list_funcs_parser.set_defaults(func=virt_list_functions)
    virt_list_node_parser.description = virt_list_nodes.__doc__
    virt_create_node_parser.description = virt_create_node.__doc__
    virt_rm_node_parser.description = virt_remove_node.__doc__
    virt_list_funcs_parser.description = virt_list_functions.__doc__
    @with_argparser(virt_parser, with_unknown_args=True)
    def do_virtual(self, opts, unknown):
        """ Virtual command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            if func.__name__ == "virt_add_function":
                func(self, opts, unknown)
            else:
                func(self, opts)
        else:
            self.do_help("virtual")

    # ------------------- APP COMMANDS ---------------------
    app_parser = argparse.ArgumentParser()
    app_sub = app_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    app_list_parser = app_sub.add_parser("list", help="list help")
    def app_list(self, opts):
        """ Lists avaliable interfaces and their status.
        """
        cmd = cmds.AppListInterfaces()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False
        for interface, status in data.items():
            if status == "enabled":
                status_string = ok_style("Enabled")
            elif status == "paused":
                status_string = warning_style("Paused")
            else:
                status_string = error_style("Disabled")
            self.poutput(f"{(interface + ':').ljust(15)} {status_string}")
        return False

    app_enable_parser = app_sub.add_parser("enable", help="enable help")
    app_enable_parser.add_argument("INTERFACE", type=str, help="Interface")
    def app_enable(self, opts):
        """ Enables an interface. """
        cmd = cmds.AppEnableInterface(opts.INTERFACE)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    app_disable_parser = app_sub.add_parser("disable", help="disable help")
    app_disable_parser.add_argument("INTERFACE", type=str, help="Interface")
    def app_disable(self, opts):
        """ Disables an interface. """
        cmd = cmds.AppDisableInterface(opts.INTERFACE)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    app_save_parser = app_sub.add_parser("save_state", help="save_state help")
    def app_save_state(self, opts):
        """ Save the current state of the active apps. Its intended use
        is just before a reboot.
        """
        cmd = cmds.AppSaveState()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    app_list_parser.set_defaults(func=app_list)
    app_enable_parser.set_defaults(func=app_enable)
    app_disable_parser.set_defaults(func=app_disable)
    app_save_parser.set_defaults(func=app_save_state)
    app_list_parser.description = app_list.__doc__
    app_enable_parser.description = app_enable.__doc__
    app_disable_parser.description = app_disable.__doc__
    app_save_parser.description = app_save_state.__doc__
    @with_argparser(app_parser)
    def do_app(self, opts):
        """ App command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("app")


    # ------------------- FAULT COMMANDS ---------------------
    fault_parser = argparse.ArgumentParser()
    fault_sub = fault_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    fault_status_parser = fault_sub.add_parser("status", help="status help")
    def fault_status(self, opts):
        """ Lists fault tolerance module status and the available
        transports.
        """
        cmd = cmds.FaultStatus()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if not data:
            return False

        na_msg = error_style("N/A")
        if "status" in data and data["status"]:
            data["status"] = ok_style("Enabled")
        else:
            data["status"] = error_style("Disabled")
        if not "transport" in data:
            data["transport"] = na_msg
        if not "strategy" in data:
            data["strategy"] = na_msg
        data["state"] = na_msg if not data["state"] else data["state"]
        data["cluster"] = na_msg if not data["cluster"] else data["cluster"]
        data["leader"] = na_msg if not data["leader"] else data["leader"]

        self.poutput("Status: " + data["status"])
        self.poutput(f"Transport: {data['transport']}")
        self.poutput(f"Strategy: {data['strategy']}")
        self.poutput(f"State: {data['state']}")
        self.poutput(f"Cluster: {data['cluster']}")
        self.poutput(f"Leader: {data['leader']}")
        return False

    fault_enable_parser = fault_sub.add_parser("enable", help="enable help")
    def fault_enable(self, opts):
        """ Enable fault tolerance module. """
        cmd = cmds.FaultEnable()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    fault_disable_parser = fault_sub.add_parser("disable", help="disable help")
    def fault_disable(self, opts):
        """ Disable fault tolerance module. """
        cmd = cmds.FaultDisable()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    fault_list_nodes_parser = fault_sub.add_parser("list_nodes",
        help="list_nodes help")
    def fault_list_nodes(self, opts):
        """ List raft nodes. """
        cmd = cmds.FaultListNodes()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Raft nodes:".format(len(data["node_list"])))
            for n in data["node_list"]:
                self.poutput("\tNode " + str(n))
        return False

    fault_new_cluster_parser = fault_sub.add_parser("new_cluster",
        help="new_cluster help")
    fault_new_cluster_parser.add_argument("CLUSTER", type=str, nargs="+",
        help="Address of the cluster nodes")
    def fault_new_cluster(self, opts):
        """ Update raft cluster. """
        cmd = cmds.FaultNewCluster(opts.CLUSTER)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput(f"{data}")
        return False

    fault_get_cluster_parser = fault_sub.add_parser("get_cluster",
        help="get_cluster help")
    def fault_get_cluster(self, opts):
        """ Download cluster from backend. """
        cmd = cmds.FaultGetCluster()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    fault_status_parser.set_defaults(func=fault_status)
    fault_enable_parser.set_defaults(func=fault_enable)
    fault_disable_parser.set_defaults(func=fault_disable)
    fault_list_nodes_parser.set_defaults(func=fault_list_nodes)
    fault_new_cluster_parser.set_defaults(func=fault_new_cluster)
    fault_get_cluster_parser.set_defaults(func=fault_get_cluster)
    fault_status_parser.description = fault_status.__doc__
    fault_enable_parser.description = fault_enable.__doc__
    fault_disable_parser.description = fault_disable.__doc__
    fault_list_nodes_parser.description = fault_list_nodes.__doc__
    fault_new_cluster_parser.description = fault_new_cluster.__doc__
    fault_get_cluster_parser.description = fault_get_cluster.__doc__
    @with_argparser(fault_parser)
    def do_fault(self, opts):
        """ Fault command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("fault")

    def do_fault_test(self, line):
        fault_cmd = json.loads(line)
        cmd = cmds.FaultTest(fault_cmd)
        self.send_cmd(cmd)
        self.recv_data()
        return False


    # ------------------- SNMP COMMANDS ---------------------
    snmp_parser = argparse.ArgumentParser()
    snmp_sub = snmp_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    snmp_get_parser = snmp_sub.add_parser("get", help="get help")
    snmp_get_parser.add_argument("HOST", type=str, help="Host IP address")
    snmp_get_parser.add_argument("COMMUNITY", type=str,
        help="Community string")
    snmp_get_parser.add_argument("OID", type=str, help="Object identifier")
    snmp_get_parser.add_argument("-v", "--version", type=int, default=2,
        choices=[1, 2], help="SNMP version, 2 by default")
    def snmp_get(self, opts):
        """ SNMP GET requests """
        cmd = cmds.SnmpGet(opts.HOST, opts.COMMUNITY, opts.OID, opts.version)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Response ({}): {}".format(*data["response"]))
        return False

    snmp_walk_parser = snmp_sub.add_parser("walk", help="walk help")
    snmp_walk_parser.add_argument("HOST", type=str, help="Host IP address")
    snmp_walk_parser.add_argument("COMMUNITY", type=str,
        help="Community string")
    snmp_walk_parser.add_argument("OID", type=str, help="Object identifier")
    snmp_walk_parser.add_argument("-v", "--version", type=int, default=2,
        choices=[1, 2], help="SNMP version (1|2)")
    def snmp_walk(self, opts):
        """ SNMP WALK requests """
        cmd = cmds.SnmpWalk(opts.HOST, opts.COMMUNITY, opts.OID, opts.version)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} values".format(len(data["response"])))
            for oid, _type, value in data["response"]:
                self.poutput(f"{oid} - {_type}: {value}")
        return False

    snmp_get_parser.set_defaults(func=snmp_get)
    snmp_walk_parser.set_defaults(func=snmp_walk)
    snmp_get_parser.description = snmp_get.__doc__
    snmp_walk_parser.description = snmp_walk.__doc__
    @with_argparser(snmp_parser)
    def do_snmp(self, opts):
        """ SNMP client command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("snmp")


    # ------------------- MODBUS COMMANDS ---------------------
    modbus_parser = argparse.ArgumentParser()
    modbus_sub = modbus_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    modbus_read_coils_parser = modbus_sub.add_parser("read_coils",
        help="read_coils help")
    modbus_read_coils_parser.add_argument("HOST", type=str,
        help="Host IP address")
    modbus_read_coils_parser.add_argument("PORT", type=int,
        help="Modbus port number")
    modbus_read_coils_parser.add_argument("ADDRESS", type=int,
        help="Start address to read from")
    modbus_read_coils_parser.add_argument("SLAVE", type=int,
        help="Modbus slave ID")
    def modbus_read_coils(self, opts):
        """ Modbus read coils requests """
        cmd = cmds.ModbusReadCoils(opts.HOST, opts.PORT, opts.ADDRESS,
                opts.SLAVE)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Response: {}".format(data["response"]))
        return False

    modbus_read_discrete_inputs_parser = modbus_sub.add_parser(
        "read_discrete_inputs", help="read_discrete_inputs help")
    modbus_read_discrete_inputs_parser.add_argument("HOST", type=str,
        help="Host IP address")
    modbus_read_discrete_inputs_parser.add_argument("PORT", type=int,
        help="Modbus port number")
    modbus_read_discrete_inputs_parser.add_argument("ADDRESS", type=int,
        help="Start address to read from")
    modbus_read_discrete_inputs_parser.add_argument("SLAVE", type=int,
        help="Modbus slave ID")
    def modbus_read_discrete_inputs(self, opts):
        """ Modbus read discrete inputs requests """
        cmd = cmds.ModbusReadDiscreteInputs(opts.HOST, opts.PORT, opts.ADDRESS,
                opts.SLAVE)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Response: {}".format(data["response"]))
        return False

    modbus_read_holding_registers_parser = modbus_sub.add_parser(
        "read_holding_registers", help="read_holding_registers help")
    modbus_read_holding_registers_parser.add_argument("HOST", type=str,
        help="Host IP address")
    modbus_read_holding_registers_parser.add_argument("PORT", type=int,
        help="Modbus port number")
    modbus_read_holding_registers_parser.add_argument("ADDRESS", type=int,
        help="Start address to read from")
    modbus_read_holding_registers_parser.add_argument("SLAVE", type=int,
        help="Modbus slave ID")
    def modbus_read_holding_registers(self, opts):
        """ Modbus read holding registers requests """
        cmd = cmds.ModbusReadHoldingRegisters(opts.HOST, opts.PORT,
                opts.ADDRESS, opts.SLAVE)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Response: {}".format(data["response"]))
        return False

    modbus_read_input_registers_parser = modbus_sub.add_parser(
        "read_input_registers", help="read_input_registers help")
    modbus_read_input_registers_parser.add_argument("HOST", type=str,
        help="Host IP address")
    modbus_read_input_registers_parser.add_argument("PORT", type=int,
        help="Modbus port number")
    modbus_read_input_registers_parser.add_argument("ADDRESS", type=int,
        help="Start address to read from")
    modbus_read_input_registers_parser.add_argument("SLAVE", type=int,
        help="Modbus slave ID")
    def modbus_read_input_registers(self, opts):
        """ Modbus read input registers requests """
        cmd = cmds.ModbusReadInputRegisters(opts.HOST, opts.PORT, opts.ADDRESS,
                opts.SLAVE)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Response: {}".format(data["response"]))
        return False


    modbus_read_coils_parser.set_defaults(func=modbus_read_coils)
    modbus_read_discrete_inputs_parser.set_defaults(
        func=modbus_read_discrete_inputs)
    modbus_read_holding_registers_parser.set_defaults(
        func=modbus_read_holding_registers)
    modbus_read_input_registers_parser.set_defaults(
        func=modbus_read_input_registers)
    modbus_read_coils_parser.description = modbus_read_coils.__doc__
    modbus_read_discrete_inputs_parser.description = \
        modbus_read_discrete_inputs.__doc__
    modbus_read_holding_registers_parser.description = \
        modbus_read_holding_registers.__doc__
    modbus_read_input_registers_parser.description = \
        modbus_read_input_registers.__doc__
    @with_argparser(modbus_parser)
    def do_modbus(self, opts):
        """ Modbus client command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("modbus")

    # ------------------- BACKEND COMMANDS ---------------------
    backend_parser = argparse.ArgumentParser()
    backend_sub = backend_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    backend_get_nodes_parser = backend_sub.add_parser("get_nodes",
        help="get_nodes help")
    def backend_get_nodes(self, opts):
        """ Download and store backend nodes """
        cmd = cmds.BackendGetNodes()
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Response: {}".format(data["response"]))
        return False

    backend_get_nodes_parser.set_defaults(func=backend_get_nodes)
    backend_get_nodes_parser.description = backend_get_nodes.__doc__
    @with_argparser(backend_parser)
    def do_backend(self, opts):
        """ Backend client command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("backend")

    # ------------------- LOCATION COMMANDS ---------------------
    location_parser = argparse.ArgumentParser()
    location_sub = location_parser.add_subparsers(title="subcommands",
        help="subcommand help")
    get_genesis_parser = location_sub.add_parser("get_genesis",
        help="get_genesis help")
    def get_genesis(self, opts):
        """ Gets the updated genesis from backend.
        """
        cmd = cmds.LocationGetGenesis()
        self.send_cmd(cmd)
        self.recv_data()
        return False

    post_genesis_parser = location_sub.add_parser("post_genesis",
        help="post_genesis help")
    def post_genesis(self, opts):
        """ Posts the modified genesis to backend.
        """
        cmd = cmds.LocationPostGenesis()
        self.send_cmd(cmd)
        self.recv_data()
        return False

    save_genesis_parser = location_sub.add_parser("save_genesis",
        help="save_genesis help")
    def save_genesis(self, opts):
        """ Saves genesis in JSON format.
        """
        cmd = cmds.LocationSaveGenesis()
        self.send_cmd(cmd)
        self.recv_data()
        return False

    list_datacenters_parser = location_sub.add_parser("list_datacenters",
        help="list_datacenters help")
    def list_datacenters(self, opts):
        """ Lists every datacenter of the genesis.
        """
        cmd = cmds.LocationListDatacenters()
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Datacenters:".format(len(data["datacenters"])))
            for datacenter in data["datacenters"]:
                self.poutput(f"\tDatacenter {datacenter['name']}")
        return False

    list_rooms_parser = location_sub.add_parser("list_rooms",
        help="list_rooms help")
    list_rooms_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    def list_rooms(self, opts):
        """ Lists every room of the given datacenter.
        """
        cmd = cmds.LocationListRooms(opts.DATACENTER)
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Rooms:".format(len(data["rooms"])))
            for row in data["rooms"]:
                self.poutput(f"\tRoom {row['name']}")
        return False

    list_rows_parser = location_sub.add_parser("list_rows",
        help="list_rows help")
    list_rows_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    list_rows_parser.add_argument("ROOM", type=str, help="Room name")
    def list_rows(self, opts):
        """ Lists every row of the given room.
        """
        cmd = cmds.LocationListRows(opts.DATACENTER, opts.ROOM)
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Rows:".format(len(data["rows"])))
            for row in data["rows"]:
                self.poutput(f"\tRow {row['name']}")
        return False

    list_containers_parser = location_sub.add_parser("list_containers",
        help="list_containers help")
    list_containers_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    list_containers_parser.add_argument("ROOM", type=str, help="Room name")
    def list_containers(self, opts):
        """ Lists every container of the given room.
        """
        cmd = cmds.LocationListContainers(opts.DATACENTER, opts.ROOM)
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Containers:".format(len(data["containers"])))
            for container in data["containers"]:
                self.poutput(f"\tContainer {container['name']}")
        return False

    list_racks_parser = location_sub.add_parser("list_racks",
        help="list_racks help")
    list_racks_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    list_racks_parser.add_argument("ROOM", type=str, help="Room name")
    list_racks_parser.add_argument("-r", "--row", type=str,
        help="Row name of the room to list")
    def list_racks(self, opts):
        """ Lists every rack of the given room.
        """
        if opts.row:
            cmd = cmds.LocationListRacks(opts.DATACENTER, opts.ROOM, opts.row)
        else:
            cmd = cmds.LocationListRacks(opts.DATACENTER, opts.ROOM)
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Racks:".format(len(data["racks"])))
            for rack in data["racks"]:
                self.poutput(f"\tRack {rack['name']}")
        return False

    list_gateways_parser = location_sub.add_parser("list_gateways",
        help="list_gateways help")
    list_gateways_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    list_gateways_parser.add_argument("ROOM", type=str, help="Room name")
    def list_gateways(self, opts):
        """ Lists every gateway of the given room.
        """
        cmd = cmds.LocationListGateways(opts.DATACENTER, opts.ROOM)
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Gateways:".format(len(data["gateways"])))
            for gateway in data["gateways"]:
                self.poutput(f"\tGateway {gateway['name']}")
        return False

    list_nodes_parser = location_sub.add_parser("list_nodes",
        help="list_nodes help")
    list_nodes_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    list_nodes_parser.add_argument("ROOM", type=str, help="Room name")
    opt_parser = list_nodes_parser.add_mutually_exclusive_group(required=False)
    opt_parser.add_argument("--row", type=str,
        help="Row name of the room to list")
    opt_parser.add_argument("--rack", type=str,
        help="Rack name of the room to list")
    def list_nodes(self, opts):
        """ Lists every node of the given room.
        """
        if opts.row:
            cmd = cmds.LocationListNodes(opts.DATACENTER, opts.ROOM,
                    row=opts.row)
        elif opts.rack:
            cmd = cmds.LocationListNodes(opts.DATACENTER, opts.ROOM,
                    rack=opts.rack)
        else:
            cmd = cmds.LocationListNodes(opts.DATACENTER, opts.ROOM)
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("{} Nodes:".format(len(data["nodes"])))
            for node in data["nodes"]:
                self.poutput(f"\tNode {node['name']}")
        return False

    move_global_parser = location_sub.add_parser("move_global",
        help="move_global help")
    move_global_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    move_global_parser.add_argument("ROOM", type=str, help="Room name")
    move_global_parser.add_argument("DISX", type=float,
        help="X distance to move, in meters")
    move_global_parser.add_argument("DISY", type=float,
        help="Y distance to move, in meters")
    def move_global(self, opts):
        """ Moves every element in the genesis (rows, racks, nodes, containers)
            a given distance.
        """
        cmd = cmds.LocationMoveGlobal(opts.DATACENTER, opts.ROOM, opts.DISX,
                opts.DISY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    move_row_parser = location_sub.add_parser("move_row", help="move_row help")
    move_row_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    move_row_parser.add_argument("ROOM", type=str, help="Room name")
    move_row_parser.add_argument("ROW", type=str, help="Row name")
    move_row_parser.add_argument("DISX", type=float,
        help="X distance to move, in meters")
    move_row_parser.add_argument("DISY", type=float,
        help="Y distance to move, in meters")
    def move_row(self, opts):
        """ Moves the given row (with its associated racks and nodes)
            a given distance.
        """
        cmd = cmds.LocationMoveRow(opts.DATACENTER, opts.ROOM, opts.ROW,
                opts.DISX, opts.DISY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    move_container_parser = location_sub.add_parser("move_container",
        help="move_container help")
    move_container_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    move_container_parser.add_argument("ROOM", type=str, help="Room name")
    move_container_parser.add_argument("CONTAINER", type=str,
        help="Container name")
    move_container_parser.add_argument("DISX", type=float,
        help="X distance to move, in meters")
    move_container_parser.add_argument("DISY", type=float,
        help="Y distance to move, in meters")
    def move_container(self, opts):
        """ Moves the given container a given distance.
        """
        cmd = cmds.LocationMoveContainer(opts.DATACENTER, opts.ROOM,
                opts.CONTAINER, opts.DISX, opts.DISY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    move_rack_parser = location_sub.add_parser("move_rack",
        help="move_rack help")
    move_rack_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    move_rack_parser.add_argument("ROOM", type=str, help="Room name")
    move_rack_parser.add_argument("RACK", type=str, help="Rack name")
    move_rack_parser.add_argument("DISX", type=float,
        help="X distance to move, in meters")
    move_rack_parser.add_argument("DISY", type=float,
        help="Y distance to move, in meters")
    def move_rack(self, opts):
        """ Moves the given rack a given distance.
        """
        cmd = cmds.LocationMoveRack(opts.DATACENTER, opts.ROOM,
                opts.RACK, opts.DISX, opts.DISY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    move_gateway_parser = location_sub.add_parser("move_gateway",
        help="move_gateway help")
    move_gateway_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    move_gateway_parser.add_argument("ROOM", type=str, help="Room name")
    move_gateway_parser.add_argument("GATEWAY", type=str, help="Gateway name")
    move_gateway_parser.add_argument("DISX", type=float,
        help="X distance to move, in meters")
    move_gateway_parser.add_argument("DISY", type=float,
        help="Y distance to move, in meters")
    def move_gateway(self, opts):
        """ Moves the given gateway a given distance.
        """
        cmd = cmds.LocationMoveGateway(opts.DATACENTER, opts.ROOM,
                opts.GATEWAY, opts.DISX, opts.DISY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    move_node_parser = location_sub.add_parser("move_node",
        help="move_node help")
    move_node_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    move_node_parser.add_argument("ROOM", type=str, help="Room name")
    move_node_parser.add_argument("NODE", type=str, help="Node name")
    move_node_parser.add_argument("DISX", type=float,
        help="X distance to move, in meters")
    move_node_parser.add_argument("DISY", type=float,
        help="Y distance to move, in meters")
    def move_node(self, opts):
        """ Moves the given node a given distance.
        """
        cmd = cmds.LocationMoveNode(opts.DATACENTER, opts.ROOM,
                opts.NODE, opts.DISX, opts.DISY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    add_room_parser = location_sub.add_parser("add_room", help="add_room help")
    add_room_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    add_room_parser.add_argument("ROOM", type=str, help="Room name")
    add_room_parser.add_argument("BUILDING", type=str, help="Building name")
    add_room_parser.add_argument("XMAX", type=float, help="X max")
    add_room_parser.add_argument("YMAX", type=float, help="Y max")
    add_room_parser.add_argument("ZMAX", type=float, help="Z max")
    def add_room(self, opts):
        """ Creates a new room.
        """
        cmd = cmds.LocationAddRoom(opts.DATACENTER, opts.ROOM, opts.BUILDING,
                opts.XMAX, opts.YMAX, opts.ZMAX)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    add_row_parser = location_sub.add_parser("add_row", help="add_row help")
    add_row_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    add_row_parser.add_argument("ROOM", type=str, help="Room name")
    add_row_parser.add_argument("ROW", type=str, help="Row name")
    add_row_parser.add_argument("ISHORIZONTAL", type=bool, help="Is horizontal")
    add_row_parser.add_argument("HOTPOS", type=float, help="Hot position")
    add_row_parser.add_argument("COLDPOS", type=float, help="Cold position")
    def add_row(self, opts):
        """ Creates a new row.
        """
        cmd = cmds.LocationAddRow(opts.DATACENTER, opts.ROOM, opts.ROW,
                opts.ISHORIZONTAL, opts.HOTPOS, opts.COLDPOS)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    add_container_parser = location_sub.add_parser("add_container",
        help="add_container help")
    add_container_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    add_container_parser.add_argument("ROOM", type=str, help="Room name")
    add_container_parser.add_argument("CONTAINER", type=str,
        help="Container name")
    add_container_parser.add_argument("XMIN", type=float, help="X minimum")
    add_container_parser.add_argument("YMIN", type=float, help="Y minimum")
    add_container_parser.add_argument("XMAX", type=float, help="X maximum")
    add_container_parser.add_argument("YMAX", type=float, help="Y maximum")
    def add_container(self, opts):
        """ Creates a new container.
        """
        cmd = cmds.LocationAddContainer(opts.DATACENTER, opts.ROOM,
            opts.CONTAINER, opts.XMIN, opts.YMIN, opts.XMAX, opts.YMAX)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    add_rack_parser = location_sub.add_parser("add_rack", help="add_rack help")
    add_rack_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    add_rack_parser.add_argument("ROOM", type=str, help="Room name")
    add_rack_parser.add_argument("ROW", type=str, help="Row name")
    add_rack_parser.add_argument("RACK", type=str, help="Rack name")
    add_rack_parser.add_argument("TYPE", type=str,
        choices=['IT', 'REFRIGERATION', 'NONE'], help="Rack type")
    add_rack_parser.add_argument("TOTALU", type=int, help="Total number of U")
    add_rack_parser.add_argument("XCENTER", type=float, help="X center")
    add_rack_parser.add_argument("YCENTER", type=float, help="Y center")
    add_rack_parser.add_argument("XSIZE", type=float, help="X size")
    add_rack_parser.add_argument("YSIZE", type=float, help="Y size")
    def add_rack(self, opts):
        """ Creates a new rack.
        """
        cmd = cmds.LocationAddRack(opts.DATACENTER, opts.ROOM, opts.ROW,
                opts.RACK, opts.TYPE, opts.TOTALU, opts.XCENTER, opts.YCENTER,
                opts.XSIZE, opts.YSIZE)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    add_gateway_parser = location_sub.add_parser("add_gateway",
        help="add_gateway help")
    add_gateway_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    add_gateway_parser.add_argument("ROOM", type=str, help="Room name")
    add_gateway_parser.add_argument("GATEWAY", type=str, help="Gateway name")
    add_gateway_parser.add_argument("DEVICEID", type=str,
        help="Device ID (MAC address)")
    add_gateway_parser.add_argument("MESHID", type=str, help="Mesh ID")
    add_gateway_parser.add_argument("X", type=float, help="X position")
    add_gateway_parser.add_argument("Y", type=float, help="Y position")
    add_gateway_parser.add_argument("Z", type=float, help="Z position")
    def add_gateway(self, opts):
        """ Creates a new gateway.
        """
        cmd = cmds.LocationAddGateway(opts.DATACENTER, opts.ROOM, opts.GATEWAY,
                opts.DEVICEID, opts.MESHID, opts.X, opts.Y, opts.Z)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    add_node_parser = location_sub.add_parser("add_node", help="add_node help")
    add_node_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    add_node_parser.add_argument("ROOM", type=str, help="Room name")
    add_node_parser.add_argument("ROW", type=str, help="Row name")
    add_node_parser.add_argument("RACK", type=str, help="Rack name")
    add_node_parser.add_argument("NODE", type=str, help="Node name")
    add_node_parser.add_argument("MAC", type=str, help="MAC address")
    add_node_parser.add_argument("MESHID", type=str, help="Mesh ID")
    add_node_parser.add_argument("UUID", type=str, help="UUID")
    add_node_parser.add_argument("UNIT", type=int, help="Unit")
    add_node_parser.add_argument("SOURCE", choices=['INLET', 'OUTLET', 'SUPPLY',
            'RETURN', 'AMBIENT', 'FLOOR', 'GRID'], type=str, help="Source")
    add_node_parser.add_argument("X", type=float, help="X position")
    add_node_parser.add_argument("Y", type=float, help="Y position")
    add_node_parser.add_argument("Z", type=float, help="Z position")
    def add_node(self, opts):
        """ Creates a new node.
        """
        cmd = cmds.LocationAddNode(opts.DATACENTER, opts.ROOM, opts.ROW,
                opts.RACK, opts.NODE, opts.MAC, opts.MESHID, opts.UUID,
                opts.UNIT, opts.SOURCE, opts.X, opts.Y, opts.Z)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    del_room_parser = location_sub.add_parser("del_room", help="del_room help")
    del_room_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    del_room_parser.add_argument("ROOM", type=str, help="Room name")
    def del_room(self, opts):
        """ Deletes an existing room.
        """
        cmd = cmds.LocationDelRoom(opts.DATACENTER, opts.ROOM)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    del_row_parser = location_sub.add_parser("del_row", help="del_row help")
    del_row_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    del_row_parser.add_argument("ROOM", type=str, help="Room name")
    del_row_parser.add_argument("ROW", type=str, help="Row name")
    def del_row(self, opts):
        """ Deletes an existing row.
        """
        cmd = cmds.LocationDelRow(opts.DATACENTER, opts.ROOM, opts.ROW)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    del_container_parser = location_sub.add_parser("del_container",
        help="add_container help")
    del_container_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    del_container_parser.add_argument("ROOM", type=str, help="Room name")
    del_container_parser.add_argument("CONTAINER", type=str,
        help="Container name")
    def del_container(self, opts):
        """ Deletes an existing container.
        """
        cmd = cmds.LocationDelContainer(opts.DATACENTER, opts.ROOM,
            opts.CONTAINER)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    del_rack_parser = location_sub.add_parser("del_rack", help="del_rack help")
    del_rack_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    del_rack_parser.add_argument("ROOM", type=str, help="Room name")
    del_rack_parser.add_argument("ROW", type=str, help="Row name")
    del_rack_parser.add_argument("RACK", type=str, help="Rack name")
    def del_rack(self, opts):
        """ Deletes an existing rack.
        """
        cmd = cmds.LocationDelRack(opts.DATACENTER, opts.ROOM, opts.ROW,
            opts.RACK)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    del_gateway_parser = location_sub.add_parser("del_gateway",
        help="del_gateway help")
    del_gateway_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    del_gateway_parser.add_argument("ROOM", type=str, help="Room name")
    del_gateway_parser.add_argument("GATEWAY", type=str, help="Gateway name")
    def del_gateway(self, opts):
        """ Deletes an existing gateway.
        """
        cmd = cmds.LocationDelGateway(opts.DATACENTER, opts.ROOM, opts.GATEWAY)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    del_node_parser = location_sub.add_parser("del_node", help="del_node help")
    del_node_parser.add_argument("DATACENTER", type=str, help="Datacenter name")
    del_node_parser.add_argument("ROOM", type=str, help="Room name")
    del_node_parser.add_argument("ROW", type=str, help="Row name")
    del_node_parser.add_argument("RACK", type=str, help="Rack name")
    del_node_parser.add_argument("NODE", type=str, help="Node name")
    def del_node(self, opts):
        """ Deletes an existing node.
        """
        cmd = cmds.LocationDelNode(opts.DATACENTER, opts.ROOM, opts.ROW,
                opts.RACK, opts.NODE)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    import_room_parser = location_sub.add_parser("import_room",
        help="import_room help")
    import_room_parser.add_argument("DATACENTER", type=str,
        help="Datacenter name")
    import_room_parser.add_argument("ROOMFILE", type=str,
        help="Room file (.JSON)")
    def import_room(self, opts):
        """ Imports a room to the genesis from a JSON file.
        """
        cmd = cmds.LocationImportRoom(opts.DATACENTER, opts.ROOMFILE)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    import_genesis_parser = location_sub.add_parser("import_genesis",
        help="import_genesis help")
    import_genesis_parser.add_argument("GENESISFILE", type=str,
        help="Genesis file (.JSON)")
    def import_genesis(self, opts):
        """ Imports a genesis to the genesis from a JSON file.
        """
        cmd = cmds.LocationImportGenesis(opts.GENESISFILE)
        self.send_cmd(cmd)
        self.recv_data()
        return False

    get_genesis_parser.set_defaults(func=get_genesis)
    post_genesis_parser.set_defaults(func=post_genesis)
    save_genesis_parser.set_defaults(func=save_genesis)
    list_datacenters_parser.set_defaults(func=list_datacenters)
    list_rooms_parser.set_defaults(func=list_rooms)
    list_rows_parser.set_defaults(func=list_rows)
    list_containers_parser.set_defaults(func=list_containers)
    list_racks_parser.set_defaults(func=list_racks)
    list_gateways_parser.set_defaults(func=list_gateways)
    list_nodes_parser.set_defaults(func=list_nodes)
    move_global_parser.set_defaults(func=move_global)
    move_row_parser.set_defaults(func=move_row)
    move_container_parser.set_defaults(func=move_container)
    move_rack_parser.set_defaults(func=move_rack)
    move_gateway_parser.set_defaults(func=move_gateway)
    move_node_parser.set_defaults(func=move_node)
    add_room_parser.set_defaults(func=add_room)
    add_row_parser.set_defaults(func=add_row)
    add_container_parser.set_defaults(func=add_container)
    add_rack_parser.set_defaults(func=add_rack)
    add_gateway_parser.set_defaults(func=add_gateway)
    add_node_parser.set_defaults(func=add_node)
    del_room_parser.set_defaults(func=del_room)
    del_row_parser.set_defaults(func=del_row)
    del_container_parser.set_defaults(func=del_container)
    del_rack_parser.set_defaults(func=del_rack)
    del_gateway_parser.set_defaults(func=del_gateway)
    del_node_parser.set_defaults(func=del_node)
    import_room_parser.set_defaults(func=import_room)
    import_genesis_parser.set_defaults(func=import_genesis)
    get_genesis_parser.description = get_genesis.__doc__
    post_genesis_parser.description = post_genesis.__doc__
    save_genesis_parser.description = save_genesis.__doc__
    list_datacenters_parser.description = list_datacenters.__doc__
    list_rooms_parser.description = list_rooms.__doc__
    list_rows_parser.description = list_rows.__doc__
    list_containers_parser.description = list_containers.__doc__
    list_racks_parser.description = list_racks.__doc__
    list_gateways_parser.description = list_gateways.__doc__
    list_nodes_parser.description = list_nodes.__doc__
    move_global_parser.description = move_global.__doc__
    move_row_parser.description = move_row.__doc__
    move_container_parser.description = move_container.__doc__
    move_rack_parser.description = move_rack.__doc__
    move_gateway_parser.description = move_gateway.__doc__
    move_node_parser.description = move_node.__doc__
    add_room_parser.description = add_room.__doc__
    add_row_parser.description = add_row.__doc__
    add_container_parser.description = add_container.__doc__
    add_rack_parser.description = add_rack.__doc__
    add_gateway_parser.description = add_gateway.__doc__
    add_node_parser.description = add_node.__doc__
    del_room_parser.description = del_room.__doc__
    del_row_parser.description = del_row.__doc__
    del_container_parser.description = del_container.__doc__
    del_rack_parser.description = del_rack.__doc__
    del_gateway_parser.description = del_gateway.__doc__
    del_node_parser.description = del_node.__doc__
    import_room_parser.description = import_room.__doc__
    import_genesis_parser.description = import_genesis.__doc__
    @with_argparser(location_parser)
    def do_location(self, opts):
        """ Location command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("location")


    # ------------------- MISC COMMANDS ---------------------
    set_log_level_parser = argparse.ArgumentParser()
    set_log_level_parser.add_argument("LOG_LEVEL", type=str, help="Log level",
        choices=["extra_debug", "debug", "info", "warning", "error", "notset"])
    set_log_level_parser.add_argument("-l", "--logger", type=str, help="Logger")
    @with_argparser(set_log_level_parser)
    def do_set_log_level(self, opts):
        if opts.LOG_LEVEL == "extra_debug":
            level = 9
        elif opts.LOG_LEVEL == "debug":
            level = logging.DEBUG
        elif opts.LOG_LEVEL == "info":
            level = logging.INFO
        elif opts.LOG_LEVEL == "warning":
            level = logging.WARNING
        elif opts.LOG_LEVEL == "error":
            level = logging.ERROR
        elif opts.LOG_LEVEL == "notset":
            level = logging.NOTSET
        else:
            level = logging.NOTSET
        self.poutput(opts.logger)
        cmd = cmds.SetLogLevelCommand(level, opts.logger)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    start_remote_client_parser = argparse.ArgumentParser()
    @with_argparser(start_remote_client_parser)
    def do_start_remote_client(self, opts):
        cmd = cmds.StartRemoteClient()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    stop_remote_client_parser = argparse.ArgumentParser()
    @with_argparser(stop_remote_client_parser)
    def do_stop_remote_client(self, opts):
        cmd = cmds.StopRemoteClient()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    start_http_logging_parser = argparse.ArgumentParser()
    @with_argparser(start_http_logging_parser)
    def do_start_http_logging(self, opts):
        cmd = cmds.StartHttpLogging()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    stop_http_logging_parser = argparse.ArgumentParser()
    @with_argparser(stop_http_logging_parser)
    def do_stop_http_logging(self, opts):
        cmd = cmds.StopHttpLogging()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    get_element_info_parser = argparse.ArgumentParser()
    get_element_info_parser.add_argument("ELEMENT", type=str,
        help="Element info")
    @with_argparser(get_element_info_parser)
    def do_get_element_info(self, opts):
        cmd = cmds.GetElementInfo(opts.ELEMENT)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data:
            self.poutput("Type: " + data["type"])
            self.poutput("Value: " + data["value"])
        return False

    show_log_parser = argparse.ArgumentParser()
    show_log_parser.add_argument("-n", "--lines", type=int, default=10,
            help="Number of lines to output, instead of the last 10")
    show_log_parser.add_argument("-g", "--grep", type=str,
            help="String PATTERNS to search for in log file.")
    show_log_parser.add_argument("-d", "--datetime", type=str,
            help="UTC datetime: \"dd/mm/yyyy HH:MM\" or \"dd/mm/yyyy HH\"")
    @with_argparser(show_log_parser)
    def do_show_log(self, opts):
        cmd = cmds.ShowLog(opts.lines, opts.grep, opts.datetime)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        self.poutput(data["log"])
        return False

    thread_list_parser = argparse.ArgumentParser()
    @with_argparser(thread_list_parser)
    def do_thread_list(self, opts):
        cmd = cmds.ThreadList()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        for thread in data["thread_list"]:
            self.poutput(f"\t{thread}")
        self.poutput("Thread stacktrace:\n")
        self.poutput(data["tb"])
        return False

    shell_remote_parser = argparse.ArgumentParser()
    shell_remote_parser.add_argument("command", type=str, nargs="+",
        help="Execute Unix command. Use 'shell_remote -- command` for " + \
            "multi-word command.")
    @with_argparser(shell_remote_parser)
    def do_shell_remote(self, opts):
        cmd = cmds.ShellRemote(opts.command)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data and data["retval"] is not None:
            self.poutput(f"[retval]\n{data['retval']}\n")
        if data and data["output"] is not None:
            self.poutput(f"[output]\n{data['output']}")
        return False

    # ------------------- SIMULATOR COMMANDS ---------------------
    simulator_parser = argparse.ArgumentParser()
    simulator_sub = simulator_parser.add_subparsers(title="subcommands",
        help="subcommand help")

    sim_start_parser = simulator_sub.add_parser("start", help="start help")
    sim_start_parser.add_argument("PERIOD", type=int,
        help="Sending rate period.")
    sim_start_parser.add_argument("NODES", type=int,
        help="Number of nodes to simulate.")
    sim_start_parser.add_argument("-s", "--seed", type=str,
        help="Random generator seed.")
    def sim_start(self, opts):
        """ Start simulator. """
        if opts.seed:
            cmd = cmds.SimulatorStart(opts.PERIOD, opts.NODES, opts.seed)
        else:
            cmd = cmds.SimulatorStart(opts.PERIOD, opts.NODES)
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    sim_stop_parser = simulator_sub.add_parser("stop", help="stop help")
    def sim_stop(self, opts):
        """ Stop simulator. """
        cmd = cmds.SimulatorStop()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        self.recv_data()
        return False

    sim_status_parser = simulator_sub.add_parser("status", help="status help")
    def sim_status(self, opts):
        """ Simulator status. """
        cmd = cmds.SimulatorStatus()
        if self.startup:
            return cmd
        self.send_cmd(cmd)
        data = self.recv_data()
        if data["running"]:
            self.poutput("Running: " + ok_style("Yes"))
        else:
            self.poutput("Running: " + error_style("No"))
        self.poutput("Period: " + str(data["period"]))
        self.poutput("Nodes: " + str(data["n_nodes"]))
        return False

    sim_status_parser.set_defaults(func=sim_status)
    sim_start_parser.set_defaults(func=sim_start)
    sim_stop_parser.set_defaults(func=sim_stop)
    sim_status_parser.description = sim_status.__doc__
    sim_start_parser.description = sim_start.__doc__
    sim_stop_parser.description = sim_stop.__doc__
    @with_argparser(simulator_parser)
    def do_simulator(self, opts):
        """ Simulator command help."""
        func = getattr(opts, "func", None)
        if func is not None:
            func(self, opts)
        else:
            self.do_help("simulator")
