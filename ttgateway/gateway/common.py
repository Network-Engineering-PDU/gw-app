import os
import re
import logging
import asyncio
from datetime import datetime as dt

from ttgwlib import Gateway, EventType
from ttgwlib import TaskOpcode as TaskOp
from ttgwlib import version
from ttgwlib.node import BOARD_IDS

import ttgateway.commands as cmds
from ttgateway.config import config


logger = logging.getLogger(__name__)


class GatewayCommon:
    """ GatewayCommon is responsible for handling the common functionalities of
    the gateway, such as configuration, initialization, start/stop operations,
    and OTA updates. The module also includes several utility  functions and
    properties related to the gateway's configuration and status.
    """
    def __init__(self, event_handler, node_db, gw_id, config_cb=None):
        """
        Initializes the GatewayCommon instance.

        :param event_handler: An event handler to manage gateway events.
        :type event_handler: class:`~ttgateway.event_handler.EventHandler`

        :param node_db: A database interface for node data.
        :type node_db: class:`~ttgateway.gateway.sqlite_database.SqliteDatabase`
            or `~ttgateway.gateway.memory_database.MemoryDatabase`

        :param gw_id: Identifier for the gateway.
        :type gw_id: str

        :param config_cb: Optional callback function for additional
            configuration.
        :type config_cb: Callable, optional
        """
        self.event_handler = event_handler
        self.node_db = node_db
        self.id = gw_id
        self.config_cb = config_cb
        self.event_handler.add_handler(EventType.SD_ENABLED,
                self.sd_enabled_handler)
        self.gw = Gateway()
        self.gw_started = False
        self.ota_in_progress = False
        self.copy_ota_in_progress = False
        self.config = None
        self.ping_task = None
        self.ping_last_ts = None

    @property
    def sleep_time(self):
        """ Gets or sets the sleep time for the gateway.

        :getter: Returns the sleep time.
        :setter: Sets the sleep time (in seconds).
        :type: integer
        """
        return config.gateway.sleep_time

    @sleep_time.setter
    def sleep_time(self, value: int):
        config.gateway.sleep_time = value
        asyncio.to_thread(config.write())

    @property
    def datetime_period(self):
        """ Gets the datetime period for the gateway.

        :return: The datetime period (in seconds).
        :rtype: integer
        """
        return config.gateway.datetime_period

    @property
    def battery_period(self):
        """ Gets the battery period for the gateway.

        :return: The battery period (in seconds).
        :rtype: integer
        """
        return config.gateway.battery_period

    @property
    def telemetry_period(self):
        """ Gets the telemetry period for the gateway.

        :return: The telemetry period (in seconds).
        :rtype: integer
        """
        return config.gateway.telemetry_period

    @property
    def co2_period(self):
        """ Gets the CO2 period for the gateway.

        :return: The CO2 period (in seconds).
        :rtype: integer
        """
        return config.gateway.co2_period

    @property
    def pwmt_period(self):
        """ Gets the power meter telemetry period for the gateway.

        :return: The power meter telemetry period (in seconds).
        :rtype: integer
        """
        return config.gateway.pwmt_period

    @property
    def ping_period(self):
        """ Gets the ping period for the gateway.

        :return: The ping period (in seconds).
        :rtype: integer
        """
        return config.gateway.ping_period

    @property
    def platform(self):
        """ Gets the platform for the gateway.

        :return: The platform.
        :rtype: str or :class:`~ttgwlib.platform.board.Platform`
        """
        return config.gateway.platform

    @property
    def version(self):
        """ Gets the version of the gateway software.

        :return: The version.
        :rtype: str
        """
        return version.VERSION

    def config_task(self, node, opcode, period, wait_time=0):
        """ Configures a task for a node.

        :param node: The node to configure.
        :type node: :class:`~ttgwlib.node.Node`

        :param opcode: The task opcode.
        :type opcode: :class:`~ttgwlib.models.task_gw.TaskOpcode`

        :param period: The period (in seconds) for the task.
        :type period: integer

        :param wait_time: The wait time (in seconds) before starting the task.
        :type wait_time: integer, optional
        """
        if config.gateway.task_config == "legacy":
            self.gw.config_task_legacy(node, opcode, period, wait_time)
        else:
            self.gw.config_task(node, opcode, period, wait_time)

    def tasks_config_cb(self, node):
        """ Callback for configuring tasks for a node.

        :param node: The node to configure.
        :type node: :class:`~ttgwlib.node.Node`
        """
        if node.board_id not in BOARD_IDS:
            logger.warning(f"Unknown board id ({node.board_id}) of node"
                + f" {node.mac.hex()}")
        self.gw.set_datetime(node)
        self.config_task(node, TaskOp.TASK_OP_REQ_DATETIME,
            self.datetime_period, self.datetime_period)
        self.config_task(node, TaskOp.TASK_OP_NRFTEMP, self.telemetry_period)

        if node.is_low_power():
            self.config_task(node, TaskOp.TASK_OP_BAT, self.battery_period)

        if node.has_co2():
            self.config_task(node, TaskOp.TASK_OP_NRFTEMP_CO2, self.co2_period)
            self.config_task(node, TaskOp.TASK_OP_NRFTEMP_START_CO2, 0)

        if node.is_power_meter():
            self.config_task(node, TaskOp.TASK_OP_PWMT_START, 0)
            self.config_task(node, TaskOp.TASK_OP_PWMT_READ, self.pwmt_period)

        if not self.config_cb is None:
            self.config_cb(self, node)

    def init(self, platform, port):
        """ Initializes the gateway.

        :param platform: Platform/board to use. It can be one of the
        following options: desktop, heimdall, cloud.
        :type platform: str or :class:`~ttgwlib.platform.board.Platform`

        :param port: For desktop platform, manually selects microcontroller
            port. If left to None, the port will be selected automatically.
            For cloud platform, this must be the network socket.
        :type port: str or socket.socket
        """
        self.gw.init(platform, port)

    def start(self, gw_config):
        """ Starts the gateway with the given configuration.

        :param gw_config: The configuration for the gateway.
        :type gw_config: :class:`~ttgwlib.config.Config`
        """
        if self.is_started():
            logger.warning("Gateway already started")
            return
        logger.debug(f"Starting gateway {self.id}")
        self.config = gw_config
        self.gw.start(gw_config)
        self.gw.add_event_handler(self.event_handler.process_event)
        self.gw.set_sleep_time(self.sleep_time)
        self.gw_started = True

    def stop(self):
        """ Stops the gateway.
        """
        if not self.is_started():
            logger.warning("Gateway not started")
            return
        logger.debug(f"Stopping gateway {self.id}")
        self.gw.stop()
        self.gw_started = False

    async def ping(self):
        """ Pings the gateway to check its connection status.

        :return: True if the gateway is connected, False otherwise.
        :rtype: bool
        """
        if self.copy_ota_in_progress or self.ota_in_progress:
            return True
        if not self.is_started():
            return False
        conn = await asyncio.to_thread(self.gw.check_connection)
        if conn:
            self.ping_last_ts = int(dt.now().timestamp())
        return conn

    def is_started(self) -> bool:
        """ Checks if the gateway is started.

        :return: True if the gateway is started, False otherwise.
        :rtype: bool
        """
        return self.gw_started

    def clear_replay_cache(self, unicast_address):
        """ Clears the replay cache for the given unicast address.

        :param unicast_address: The unicast address to clear the cache for.
        :type unicast_address: integer
        """
        self.gw.dev_manager.clear_replay_cache(unicast_address)

    async def save_db_backup(self):
        """ Saves a backup of the database.
        """
        def sabe_db_backup_blocking():
            backups_dir = f"{config.TT_DIR}/backups"
            os.makedirs(backups_dir, exist_ok=True)
            last_db_index = 0
            for db in os.listdir(backups_dir):
                match = re.search("database(\d+)\.json", db)
                if match:
                    last_db_index = max(last_db_index, int(match.groups()[0]))
            last_db_index += 1
            os.system(f"cp {config.TT_DIR}/mesh_database.json "
                + f"{backups_dir}/database{last_db_index}.json")
        await asyncio.to_thread(sabe_db_backup_blocking)

    def sd_enabled_handler(self, event):
        """ Handler for softdevice enabled events.

        :param event: The event object.
        :type event: class:`~ttgateway.events.Event`
        """
        if self.ota_in_progress:
            self.ota_in_progress = False
            if self.copy_ota_in_progress:
                self.copy_ota_in_progress = False
                logger.info("Copy OTA finished")
            else:
                logger.info("OTA finished")

    async def send_ota(self, delay, nodes):
        """ Sends an OTA update after a delay.

        :param delay: The delay (in seconds) before sending the OTA update.
        :type delay: integer
        :param nodes: The nodes to send the OTA update to.
        :type nodes: list of class:`~ttgwlib.node.Node`
        """
        if delay > 30:
            await asyncio.sleep(delay-30)
            logger.debug("30 seconds for OTA update")
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(delay)
        self.ota_in_progress = True
        logger.info("Sending OTA update")
        await asyncio.to_thread(self.gw.ota_helper.send_update)
        self.event_handler.add_handler(EventType.WAKE_NOTIFY,
                self.ota_node_reset_handler)

    def ota_node_reset_handler(self, event):
        """ Handler for OTA node reset events.

        :param event: The event object.
        :type event: class:`~ttgateway.events.Event`
        """
        if event.node in self.gw.models.ota.pending_nodes:
            logger.info("Asking ota status to node " + str(event.node))
            self.gw.get_node_ota_status(event.node)
            self.gw.models.ota.pending_nodes.remove(event.node)

        if len(self.gw.models.ota.pending_nodes) == 0:
            logger.info("No more nodes to ask status")
            self.event_handler.remove_handler(self.ota_node_reset_handler)


    async def ota_notify_nodes(self, event_time, nodes, data, ota_type):
        """ Notifies nodes of an OTA update.

        :param event_time: The time of the event.
        :type event_time: datetime

        :param nodes: The nodes to notify.
        :type nodes: list of class:`~ttgwlib.node.Node`

        :param data: The data for the OTA update.
        :type data: dict

        :param ota_type: The type of OTA update.
        :type ota_type: class:`~ttgwlib.ota_helper.OtaType`
        """
        self.gw.models.ota.clear_pending_nodes()

        while self.copy_ota_in_progress:
            await asyncio.sleep(1)

        for node in nodes:
            self.gw.models.ota.update_notify(node, ota_type,
                    data["major"], data["minor"], data["fix"],
                    data["sd_version"], data["size"],
                    int(event_time.timestamp()))

    async def dispatch(self, command) -> cmds.Response:
        """ Dispatches a command to the gateway.

        :param command: The command to dispatch.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response from the command.
        :rtype: class:`~ttgateway.commands.Response`
        """
        if self.ota_in_progress:
            return command.response("Busy: OTA in progress", False)

        if isinstance(command, cmds.GatewayCheck):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            conn = await asyncio.to_thread(self.gw.check_connection)
            return command.response(extra_data={"connection_alive": conn})

        if isinstance(command, cmds.GatewayStartScan):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            uuid_filter = ['DA51']
            self.gw.start_scan(uuid_filter, timeout=command.timeout,
                one=command.one)
            return command.response()

        if isinstance(command, cmds.GatewayStopScan):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            self.gw.stop_scan()
            await self.save_db_backup()
            return command.response()

        if isinstance(command, cmds.GatewayStatus):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            status = self.gw.get_status()
            status["app_version"] = config.VERSION
            return command.response(extra_data=status)

        if isinstance(command, cmds.GatewayGetSleep):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            return command.response(extra_data={"sleep_time": self.sleep_time})

        if isinstance(command, cmds.GatewaySetSleep):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            old_time = self.sleep_time
            self.sleep_time = command.time
            self.gw.set_sleep_time(self.sleep_time)
            extra_data = {
                "old_sleep_time": old_time,
                "new_sleep_time": self.sleep_time
            }
            return command.response(extra_data=extra_data)

        if isinstance(command, cmds.GatewayConfigMesh):
            lib_config = self.node_db.get_config()
            if command.netkey:
                lib_config.netkey = bytes.fromhex(command.netkey)
            if command.unicast_address:
                lib_config.unicast_address = command.unicast_address
            self.node_db.store_config(lib_config)
            if self.is_started():
                self.gw.reset()
            return command.response()

        if isinstance(command, cmds.GatewayListener):
            if not self.is_started():
                return command.response("Gateway not initialized", False)
            self.gw.set_listener(command.value)
            return command.response()

        logger.warning(f"Unknown command {type(command)}")
        return command.response("Unknown command", False)
