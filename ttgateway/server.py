import os
import logging
import asyncio
import re
from datetime import datetime as dt
import threading
import faulthandler
import tempfile

import ttgateway.commands as cmds
from ttgateway.config import config
from ttgateway import utils
from ttgateway.gateway.gateway_manager import GatewayManager
from ttgateway.event_handler import EventHandler
from ttgateway.apps.app_manager import AppManager
from ttgateway.leds import get_led_controller, DummyGpioController
from ttgateway.remote_ws_client import RemoteWebsocketClient
from ttgateway.location.location_manager import LocationManager
from ttgateway.virtual.virtual_manager import VirtualManager
from ttgateway.http_handler import HttpHandler
from ttgateway.simulator import Simulator


logger = logging.getLogger(__name__)
obj = None # Global variable for get_element_info command


class Server:
    """ Server class is responsible for managing a server with various
    functionalities including LED control, fault tolerance, node management,
    and command processing.
    """
    def __init__(self):
        """ Initializes the Server instance.
        """
        self.led_controller = None
        self.led_control_task = None
        self.fault_manager = None
        self.node_db = None
        self.event_handler = None
        self.gateway = None
        self.gw_manager = None
        self.app_manager = None
        self.remote_client = None
        self.location_manager = None
        self.virtual_manager = None
        self.http_handler = None
        self.snmp_client = None
        self.modbus_client = None
        self.simulator = None
        self.server = None

    async def init(self):
        """ Reads the configuration file and initializes all the server
        components, including the gateway manager, the node database, the
        event handler, the fault tolerance manager, and the LED controller.
        """
        if not hasattr(asyncio, "to_thread"): #TODO: Remove when python3.9
            logger.debug("Using custom to_thread function")
            from ttgateway.to_thread_helper import to_thread
            asyncio.to_thread = to_thread

        if not config.config_file_exists():
            config.create_default_config()
        config.read()
        self.led_controller = get_led_controller()
        self.event_handler = EventHandler(self.led_controller)
        node_db_file = f"{config.TT_DIR}/mesh_nodes.db"
        try:
            from ttgateway.fault_tolerance import FaultManager
            from ttgateway.fault_tolerance import RaftSqliteDatabase
            self.fault_manager = FaultManager(self)
            self.node_db = RaftSqliteDatabase(node_db_file, self.fault_manager)
        except ImportError:
            logger.debug("ttraft is not installed")
            if config.gateway.node_db == "sqlite":
                from ttgateway.gateway.sqlite_database import SqliteDatabase
                self.node_db = SqliteDatabase(node_db_file)
            elif config.gateway.node_db == "memory":
                from ttgateway.gateway.memory_database import MemoryDatabase
                self.node_db = MemoryDatabase()
                backend = self.app_manager.interfaces["backend"]
                await backend.get_nodes()

        try:
            from ttgateway.snmp_client import SnmpClient
            self.snmp_client = SnmpClient()
        except ImportError:
            logger.debug("netsnmp is not installed")
            self.snmp_client = None

        try:
            from ttgateway.modbus_client import ModbusClient
            self.modbus_client = ModbusClient()
        except ImportError:
            logger.debug("pymodbus is not installed")
            self.modbus_client = None

        self.node_db.start()
        self.app_manager = AppManager(self)
        self.gw_manager = GatewayManager(self)
        await self.gw_manager.gateway_mngr_check()
        self.remote_client = RemoteWebsocketClient(self)
        self.location_manager = LocationManager()
        self.virtual_manager = VirtualManager(self)
        self.simulator = Simulator(self.event_handler)
        asyncio.create_task(self.event_handler.run_handlers())
        self.http_handler = HttpHandler()
        self.http_handler.setLevel(25) # Between INFO and WARNING
        _logger = logging.getLogger()
        _logger.addHandler(self.http_handler)

    async def _clean_exit(self):
        """ Performs a clean shutdown of the server by stopping all active tasks
        and components gracefully, including the node database, gateway manager,
        application manager, LED controller, remote client, HTTP handler, fault
        manager, virtual manager, and event handler.
        """
        self.node_db.stop()
        await self.gw_manager.gateway_mngr_stop()
        await self.gw_manager.stop_remote_server()
        await self.app_manager.pause()
        self.led_controller.status_stopped()
        if self.led_control_task:
            self.led_control_task.cancel()
        self.remote_client.stop()
        self.http_handler.stop()
        if self.fault_manager:
            await self.fault_manager.stop()
        self.virtual_manager.stop_all()

        await self.event_handler.stop_handler()

        await asyncio.sleep(3)

        tasks = asyncio.all_tasks()
        n_tasks = len(tasks) - 2
        if n_tasks > 0:
            logger.warning(f"{n_tasks} task{'s' if n_tasks > 1 else ''} " + \
                "still active, stopping anyways")

        self.server.close()

    def clean_exit(self):
        """ Initiates the clean exit process.
        """
        asyncio.create_task(self._clean_exit())

    async def process_command(self, command):
        """ Processes a given command by dispatching it to the appropriate
        handler based on the command type. It is the main command dispatcher.

        :param command: The command to process.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response from processing the command.
        :rtype: class:`~ttgateway.commands.Response`
        """
# pylint: disable=bare-except
        try:
            if isinstance(command, (cmds.GatewayMngrCommand,
                    cmds.GatewayCommand)):
                resp = await self.gw_manager.dispatch(command)
            elif isinstance(command, cmds.AppCommand):
                resp = await self.app_manager.process_commands(command)
            elif isinstance(command, cmds.FaultCommand):
                if self.fault_manager:
                    resp = await self.fault_manager.process_command(command)
                else:
                    resp = command.response("ttraft is not installed", False)
            elif isinstance(command, cmds.LocationCommand):
                resp = await self.location_manager.process_command(command)
            elif isinstance(command, cmds.VirtualCommand):
                resp = await self.virtual_manager.dispatch(command)
            elif isinstance(command, cmds.ConfigCommand):
                resp = await self.dispatch_config(command)
            elif isinstance(command, cmds.SnmpCommand):
                if self.snmp_client:
                    resp = await self.snmp_client.process_command(command)
                else:
                    resp = command.response("netsnmp is not installed", False)
            elif isinstance(command, cmds.ModbusCommand):
                if self.modbus_client:
                    resp = await self.modbus_client.process_command(command)
                else:
                    resp = command.response("pymodbus is not installed", False)
            elif isinstance(command, cmds.SimulatorCommand):
                resp = await self.simulator.process_command(command)
            else:
                resp = await self.dispatch(command)
            return resp
        except:
            logger.exception("Error processing command")
            return command.response("Error processing command", False)
# pylint: enable=bare-except

    async def startup_commands(self):
        """ Executes startup commands from a configuration file, if it exists.
        """
        gwrc_path = f"{config.TT_DIR}/gwrc"
        if os.path.isfile(gwrc_path):
            from ttgateway.cli_client import CLIClient
            client = CLIClient(startup=True)

            with open(gwrc_path) as gwrc:
                lines = gwrc.readlines()

            for line in lines:
                words = line.split()
                gwrc_cmd = words[0]
                gwrc_args = words[1:] if len(words) > 1 else []

                if gwrc_cmd[0] == "#":
                    continue

                parser = getattr(client, f"{gwrc_cmd}_parser", None)
                if parser:
                    args = parser.parse_args(gwrc_args)
                    if hasattr(args, "func"):
                        command = args.func(client, args)
                    else:
                        func = getattr(client, f"do_{gwrc_cmd}").__wrapped__
                        command = func(client, args)
                    await self.process_command(command)
                else:
                    logger.warning(f"Invalid startup cmd: {gwrc_cmd}")

    async def server_cb(self, reader, writer):
        """ Handles incoming server connections by reading data, processing
        commands, and sending responses back to the client.

        :param reader: Stream reader for incoming data.
        :type reader: asyncio.StreamReader

        :param writer: Stream writer for outgoing data.
        :type writer: asyncio.StreamWriter
        """
        try:
            data_length = int.from_bytes(await reader.read(4), "little")
            data = await reader.read(data_length)
            command = cmds.SerialMessage.deserialize(data)
            resp = await self.process_command(command)
            writer.write(resp.serialize())
            await writer.drain()
        finally:
            writer.close()

    async def run_server(self):
        """ Initializes and runs the server, including startup commands and
        LED control.
        """
        await self.init()
        await self.startup_commands()

        self.led_control_task = asyncio.create_task(self.led_control())

        self.server = await asyncio.start_unix_server(self.server_cb,
            config.SERVER_SOCKET)
        async with self.server:
            await self.server.serve_forever()

        await asyncio.sleep(2)

    def run(self):
        """ Runs the server using the asyncio event loop and handles any
        remaining threads upon exit.
        """
        try:
            asyncio.run(self.run_server())
        except asyncio.CancelledError:
            logger.info("Asyncio loop finished")

        n_threads = len(threading.enumerate()) - 1
        if n_threads > 0:
            logger.warning(
                f"{n_threads} thread{'s' if n_threads > 1 else ''} " + \
                "still running, stopping anyways")

            for th in threading.enumerate():
                logger.debug(f"Thread: {th.getName()}")

        logger.info("Exit")


    async def dispatch(self, command) -> cmds.Response:
        """ Dispatches the server commands to the appropriate handler and
        returns the response.

        :param command: The command to dispatch.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response from dispatching the command.
        :rtype: class:`~ttgateway.commands.Response`
        """
        logger.debug(f"Command received: {type(command).__name__}")

        if isinstance(command, cmds.SetLogLevelCommand):
            if command.logger:
                logging.getLogger(command.logger).setLevel(command.log_level)
            else:
                logging.getLogger().setLevel(command.log_level)
            return command.response()

        if isinstance(command, cmds.StartRemoteClient):
            self.remote_client.start()
            return command.response()

        if isinstance(command, cmds.StopRemoteClient):
            self.remote_client.stop()
            return command.response()

        if isinstance(command, cmds.StartHttpLogging):
            self.http_handler.start()
            return command.response()

        if isinstance(command, cmds.StopHttpLogging):
            self.http_handler.stop()
            return command.response()

        if isinstance(command, cmds.GetElementInfo):
            g = globals()
            g["self"] = self
            try:
                exec(f"obj = self.{command.element}", globals())
            except AttributeError:
                return command.response("Error: Object does not exits", False)
            except TypeError:
                return command.response("Error calling function", False)
            except SyntaxError:
                return command.response("Error: Syntax error", False)
            except IndexError:
                return command.response("Error: Index error", False)

            extra_data = {
                "type": str(type(obj)),
                "value": str(obj)
            }
            return command.response(extra_data=extra_data)

        if isinstance(command, cmds.ShowLog):
            log_path_base = f"{config.TT_DIR}/logs/log"
            if not os.path.isfile(log_path_base):
                return command.response("Log file not found.", False)
            result = ""
            n_lines = 0
            log_count = 0
            log_path = log_path_base
            while (n_lines <= command.lines) and os.path.isfile(log_path):
                lines_to_read = command.lines - n_lines
                result += utils.tail(log_path, lines_to_read).decode()
                n_lines = result.count("\n")
                log_count += 1
                log_path = f"{log_path_base}.{log_count}"
            if command.datetime:
                if re.match("[0-9]{1,2}\/[0-9]{1,2}/[0-9]{4} [0-9]{1,2}$",
                        command.datetime):
                    log_t = dt.strptime(command.datetime, "%d/%m/%Y %H")
                    datetime_pattern = log_t.strftime("%Y-%m-%d %H")
                else:
                    log_t = dt.strptime(command.datetime, "%d/%m/%Y %H:%M")
                    datetime_pattern = log_t.strftime("%Y-%m-%d %H:%M")
                matches = []
                for line in result.splitlines():
                    if re.match(datetime_pattern, line):
                        matches.append(line)
                result = "\n".join(matches)
            if command.grep:
                matches = []
                for line in result.splitlines():
                    if re.search(command.grep, line):
                        matches.append(line)
                result = "\n".join(matches)
            return command.response(extra_data={"log": result})

        if isinstance(command, cmds.ShellRemote):
            if not command.command:
                return command.response("Invalid command.", False)
            retval, output = await utils.shell(command.command, timeout=120)
            if retval is None:
                return command.response(
                    f"Invalid command: {command.command}", False)
            return command.response(
                extra_data={"retval": retval, "output": output})

        if isinstance(command, cmds.BackendGetNodes):
            backend = self.app_manager.interfaces["backend"]
            await backend.get_nodes()
            return command.response()

        if isinstance(command, cmds.ThreadList):
            thread_list = []
            for th in threading.enumerate():
                th_name = f"{th.getName()}, 0x{th.ident:08x}"
                thread_list.append(th_name)
            with tempfile.TemporaryFile() as tmp:
                faulthandler.dump_traceback(file=tmp, all_threads=True)
                tmp.seek(0)
                tb_str = tmp.read().decode("utf-8")
                #logger.info(f"Stacktrace {tmp.name}: {tb_str}")
            return command.response(f"{len(thread_list)} active threads",
                    extra_data={"thread_list": thread_list, "tb": tb_str})

        logger.warning(f"Unknown command {type(command)}")
        return command.response("Unknown command", False)

    async def dispatch_config(self, command) -> cmds.Response:
        """ Dispatches a configuration command to the appropriate handler and
        returns the response.

        :param command: The configuration command to dispatch.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response from dispatching the command.
        :rtype: class:`~ttgateway.commands.Response`
        """
        logger.debug(f"Command received: {type(command).__name__}")

        if isinstance(command, cmds.ConfigSet):
            if command.module == "netkey":
                self.node_db.set_netkey(bytes.fromhex(command.value))
            elif command.module == "address":
                self.node_db.set_address(int(command.value))
            elif command.module in config.config:
                if command.field in config.config[command.module]:
                    v_type = type(config.config[command.module][command.field])
                    try:
                        value = v_type(command.value)
                    except ValueError:
                        return command.response("Invalid value type", False)
                    config.config[command.module][command.field] = value
                else:
                    return command.response("Invalid field", False)
            else:
                return command.response("Invalid module", False)
            return command.response()

        if isinstance(command, cmds.ConfigGet):
            if command.module == "netkey":
                value = self.node_db.get_netkey().hex()
            elif command.module == "address":
                value = self.node_db.get_address()
            elif command.module in config.config:
                if command.field in config.config[command.module]:
                    value = config.config[command.module][command.field]
                else:
                    return command.response("Invalid field", False)
            else:
                return command.response("Invalid module", False)
            extra_data = {"value": value}
            return command.response(extra_data=extra_data)

        if isinstance(command, cmds.ConfigSave):
            await asyncio.to_thread(config.write)
            return command.response()

        if isinstance(command, cmds.ConfigBackup):
            await asyncio.to_thread(self.node_db.backup)
            await asyncio.to_thread(config.create_backup_config)
            return command.response()

        if isinstance(command, cmds.ConfigErase):
            await asyncio.to_thread(self.node_db.erase)
            return command.response()

        logger.warning(f"Unknown command {type(command)}")
        return command.response("Unknown command", False)

    async def led_control(self):
        """ Controls the LED status based on Internet connectivity and NTP
        synchronization status.
        """
        if self.led_controller != DummyGpioController:
            logger.debug(f"Led controller: {self.led_controller.__name__}")

        self.led_controller.status_started()

        status = "LINK_NOT_CONNECTED"
        try:
            while True:
                connected = await asyncio.to_thread(
                    utils.check_internet_connection)
                ntp_is_sync = await utils.ntp_is_sync()
                if not ntp_is_sync and connected:
                    await utils.ntp_restart()
                if status == "LINK_NOT_CONNECTED" and connected:
                    await asyncio.to_thread(self.led_controller.link_connected)
                    status = "LINK_CONNECTED"
                elif status == "LINK_CONNECTED" and not connected:
                    await asyncio.to_thread(
                        self.led_controller.link_not_connected)
                    status = "LINK_NOT_CONNECTED"
                await asyncio.sleep(30)
        except asyncio.exceptions.CancelledError:
            logger.info("Led control closed")
            return
