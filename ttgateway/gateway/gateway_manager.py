
import asyncio
import json
import logging
import os
import ssl
import threading
from datetime import timedelta
from datetime import datetime as dt
from enum import Enum, auto

from ttgwlib import Config
from ttgwlib import EventType as LibEventType
from ttgwlib import OtaType

from ttgateway import utils
from ttgateway.config import config
from ttgateway.gateway.remote import GatewayRemote
from ttgateway.gateway.local import GatewayLocal
from ttgateway.gateway.node_data import NodeData
from ttgateway.gateway.whitelist_manager import WhitelistManager
import ttgateway.commands as cmds


logger = logging.getLogger(__name__)


class GatewayRole(Enum):
    """ Enum defining various roles for a gateway. """
    STANDALONE = auto()
    PASSTHROUGH = auto()
    SERVER = auto()
    FAULT = auto()


GW_ROLE_NAME = {
    "standalone"  : GatewayRole.STANDALONE,  # standalone mode
    "passthrough" : GatewayRole.PASSTHROUGH, # passthrough mode
    "server"      : GatewayRole.SERVER,      # server mode
    "fault"       : GatewayRole.FAULT,       # fault tolerance mode
}


class GatewayTaskStatus(Enum):
    """ Enum defining the possible status of a GatewayTask. """
    SUCCESS = auto()
    NO_GW = auto()
    NO_FUNC = auto()
    NO_NODE = auto()
    ERROR = auto()


class GatewayTaskResult:
    """ Represents the result of a GatewayTask executed by a gateway. """
    def __init__(self, status: GatewayTaskStatus, info: str):
        """ Initializes GatewayTaskResult.

        :param status: Status of the task.
        :type status:
            class:`~ttgateway.gateway.gateway_manager.GatewayTaskStatus`

        :param info: Additional information about the task result.
        :type info: str
        """
        self.status = status
        self.info = info

    def success(self):
        return self.status == GatewayTaskStatus.SUCCESS


class GatewayTask:
    """ Represents a task to be executed by a gateway. """
    def __init__(self, gw_manager, node, func):
        """ Initializes a GatewayTask.

        :param gw_manager: Reference to the GatewayManager.
        :type gw_manager:
            class:`~ttgateway.gateway.gateway_manager.GatewayManager`

        :param node: Node associated with the task.
        :type node: class:`~ttgwlib.gateway.Gateway`

        :param func: Function to be executed for the task.
        :type func: Callable
        """
        self.node = node
        self.gw_manager = gw_manager # Not ideal
        self.func = func
        self.gateway = None

    def execute(self):
        """ Executes the task, checking the availability and status of the
        gateway and node.

        :return: Task result indicating the result of the task execution.
        :rtype: class:`~ttgateway.gateway.gateway_manager.GatewayTaskResult`
        """
        self.gateway = self.gw_manager.get_gateway_by_node(self.node)
        if not self.gw_manager.gateways:
            error = "No available gateways. "
            return GatewayTaskResult(GatewayTaskStatus.ERROR, error)
        if self.gateway is None:
            error = f"Gateway not found for {self.node}. "
            return GatewayTaskResult(GatewayTaskStatus.NO_GW, error)
        if not self.gateway.is_started():
            error = f"Gateway not initialized for {self.node}. "
            return GatewayTaskResult(GatewayTaskStatus.NO_GW, error)
        if self.node is None:
            error = f"Node {self.node} not found. "
            return GatewayTaskResult(GatewayTaskStatus.NO_NODE, error)
        if self.func is None:
            error = f"Function {self.func} not found. "
            return GatewayTaskResult(GatewayTaskStatus.NO_FUNC, error)
        self.func(self)
        return GatewayTaskResult(GatewayTaskStatus.SUCCESS, "")


class GatewayManagerConfig:
    """ Configuration for the Gateway Manager.
    """
    def __init__(self, role, address):
        """Initialize GatewayManagerConfig

        :param role: Role of the gateway.
        :type role: class:`~ttgateway.gateway.gateway_manager.GatewayRole`

        :param address: IP or unicast address of the gateway.
        :type address: str or integer
        """
        self.role = role
        self.address = address


class GatewayManager:
    """ GatewayManager class is responsible for managing and controlling
    multiple gateways.

    It initializes and manages local and remote gateways, handles connectivity
    and disconnection events, schedules and executes tasks for its nodes, and
    processes incoming events based on their whitelists.

    The class supports multiple operational modes such as passthrough,
    standalone, or server mode and handles the configuration, starting,
    stopping, and pinging of gateways.

    It also includes mechanisms for task queuing, event filtering, and replay
    caching messages between the gateways and its nodes.
    """
    def __init__(self, server, tls=True):
        """ Initialize GatewayManager

        :param server: Reference to the server instance.
        :type server: class:`~ttgateway.server.Server`

        :param tls: Boolean indicating if TLS should be used.
        :type tls: bool
        """
        self.server = server
        self.node_db = server.node_db
        self.event_handler = server.event_handler
        self.event_handler.add_handler(LibEventType.UART_DISCONNECTION,
                self.uart_disconnection_cb)
        self.tls = tls
        self.node_data = NodeData(self.event_handler)
        self.wl_manager = WhitelistManager()
        self.replay_cache = {}
        self.remote_server = None
        self.id_count = 0
        self.active = 0
        self.gateways = [] # Active gateways in this gateway manager
        self.local_gateways = [] # Gateways physically connected
        self.passthrough_gw = None # TODO: multiple passthrough gateways
        self.started = False
        self.task_queue = {} # Dict[node, Queue[GatewayTask]]
        self.cmd_handlers = {
            cmds.GatewayMngrInit: self.gateway_mngr_init_cmd,
            cmds.GatewayMngrUninit: self.gateway_mngr_uninit_cmd,
            cmds.GatewayMngrList: self.gateway_mngr_list,
            cmds.GatewayMngrCheckPT: self.gateway_mngr_check_pt_connection,
            cmds.NodeList: self.node_list,
            cmds.NodeSummary: self.node_summary,
            cmds.NodeCancelTasks: self.node_cancel_tasks,
            cmds.NodeReset: self.node_reset,
            cmds.NodeRate: self.node_rate,
            cmds.NodeRssiStart: self.node_rssi_start,
            cmds.NodeRssiGet: self.node_rssi_get,
            cmds.NodeRssiPing: self.node_rssi_ping,
            cmds.NodeAccelOff: self.node_accel_off,
            cmds.NodeOta: self.node_ota,
            cmds.NodeTaskCreate: self.node_task_create,
            cmds.NodeTaskDelete: self.node_task_delete,
            cmds.NodeTaskModify: self.node_task_modify,
            cmds.NodeTasksGet: self.node_tasks_get,
            cmds.NodeOtaStatus: self.node_ota_status,
            cmds.NodeBeaconStart: self.node_beacon_start,
            cmds.NodeBeaconStop: self.node_beacon_stop,
            cmds.NodeSetPwmtConfig: self.node_set_pwmt_config,
            cmds.NodeSetPwmtConv: self.node_set_pwmt_conv,
            cmds.NodeTempMode: self.node_temp_mode,
            cmds.NodeCalibrate: self.node_calibrate,
            cmds.NodeResetCalibration: self.node_reset_calibration,
            cmds.NodeSetDAC: self.node_set_dac,
            cmds.NodeSetRelay: self.node_set_relay,
            cmds.NodeSetFailsafe: self.node_set_failsafe,
            cmds.NodeSendOutVector: self.node_send_out_vector,
            cmds.NodeOutputStatus: self.node_output_status,
            cmds.NodeReboot: self.node_reboot,
        }

    @property
    def server_host(self):
        """ Returns the server IP address.
        """
        return config.multi_gw_server.host

    @property
    def ca_cert(self):
        """ Returns the CA certificate path.
        """
        return config.multi_gw_server.ca_cert

    @property
    def server_cert(self):
        """ Returns the server certificate path.
        """
        return config.multi_gw_server.server_cert

    @property
    def server_key(self):
        """ Returns the server key path.
        """
        return config.multi_gw_server.server_key

    @property
    def client_cert(self):
        """ Returns the client certificate path.
        """
        return config.multi_gw_client.client_cert

    @property
    def client_key(self):
        """ Returns the client key path.
        """
        return config.multi_gw_client.client_key

    @property
    def server_port(self):
        """ Returns the server port.
        """
        return config.multi_gw_server.port

    @property
    def remote_ping_period(self):
        """ Returns the remote ping period.
        """
        return config.multi_gw_server.ping_period

    @property
    def platform(self):
        """ Returns the gateway platform.
        """
        return config.gateway.platform

    @property
    def role(self):
        """ Returns the role of the gateway manager.
        """
        return GW_ROLE_NAME[config.gateway.multi_gw_role]

    def add_gateway(self, gateway):
        """ Adds a gateway to the gateway manager.

        :param gateway: The gateway to be added.
        :type gateway: class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`

        :return: The new ID count.
        :rtype: integer
        """
        self.gateways.append(gateway)
        self.id_count += 1
        self.active += 1
        return self.id_count

    def remove_gateway(self, gateway):
        """ Removes a gateway from the gateway manager.

        :param gateway: The gateway to be removed.
        :type gateway: class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        if gateway in self.gateways:
            self.gateways.remove(gateway)
            self.active -= 1

    async def ping_gateway(self, gateway):
        """ Pings a gateway to check its connectivity.

        :param gateway: The gateway to ping.
        :type gateway: class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        conn = await gateway.ping()
        if not conn:
            logger.info(f"Ping failed: Gateway {gateway.id}")
            await self.disconnection_cb(gateway)

    def ping_node(self, node):
        """ Pings a node to check its connectivity.

        :param node: The node to ping.
        :type node: class:`~ttgwlib.gateway.Gateway`

        :return: An asyncio task.
        :rtype: class:`asyncio.Task`
        """
        return asyncio.create_task(self._ping_node(node))

    async def _ping_node(self, node):
        """ Pings a node and assigns it to a gateway if necessary.

        :param node: The node to ping.
        :type node: class:`~ttgwlib.node.Node`

        :return: True if the node was assigned to a gateway, otherwise False.
        :rtype: bool
        """
        assigned_gateway = self.get_gateway_by_node(node)
        if not assigned_gateway:
            logger.debug(f"{node} is not assigned to any gateway")
            for gateway in self.gateways:
                if assigned_gateway:
                    break
                logger.debug(f"{node} ping from {gateway.id}")
                gateway.gw.ping_to_node(node)
                await asyncio.sleep(10)
                assigned_gateway = self.get_gateway_by_node(node)
        else:
            assigned_gateway.gw.ping_to_node(node)
        if not assigned_gateway:
            logger.debug(f"{node} could not be assigned to any gateway")
            return False
        logger.debug(f"{node} is assigned to gateway {assigned_gateway.id}")
        self.execute_pending_tasks(node)
        return True

    def task_schedule(self, task):
        """ Schedules a task for execution.

        If the task is not an instance of `GatewayTask`, it returns an error
        result. Otherwise, it executes the task. If the execution result
        indicates that  no gateway is available (`NO_GW` status), the task is
        queued for later  execution, and a ping is sent to the node associated
        with the task.

        :param task: Task to be scheduled.
        :type task: class:`~ttgateway.gateway.gateway_manager.GatewayTask`

        :return: Result of the task execution.
        :rtype: class:`~ttgateway.gateway.gateway_manager.GatewayTaskResult`
        """
        if not isinstance(task, GatewayTask):
            return GatewayTaskResult(GatewayTaskStatus.ERROR, "Invalid task")
        result = task.execute()
        if result.status == GatewayTaskStatus.NO_GW:
            result.info += "Task queued"
            if not task.node in self.task_queue:
                self.task_queue[task.node] = asyncio.Queue()
            self.task_queue[task.node].put_nowait(task)
            self.ping_node(task.node)
        return result

    def execute_pending_tasks(self, node):
        """ Executes pending tasks for a specific node.

        Retrieves tasks from the queue associated with the node and executes
        them one by one. Stops execution if any task does not succeed.

        :param node: Node for which to execute pending tasks.
        :type node: class:`~ttgwlib.node.Node`
        """
        if not node in self.task_queue:
            return
        while not self.task_queue[node].empty():
            task = self.task_queue[node].get_nowait()
            status = task.execute()
            if status != GatewayTaskStatus.SUCCESS:
                return

    async def uart_disconnection_cb(self, event):
        """ Callback for handling UART disconnection events.

        :param event: Disconnection event.
        :type event: class:`~ttgateway.events.Event`
        """
        for gateway in self.gateways:
            if gateway.gw == event.gw:
                await self.disconnection_cb(gateway)

    def ping_task_stop(self, gateway):
        """ Stops gateway ping task.
        """
        if gateway.ping_task:
            gateway.ping_task.cancel()
        else:
            logger.warning("Ping task does not exist")

    async def stop_gateway(self, gateway):
        """ Stops a gateway.

        For remote gateways, closes the connection and removes the gateway from
        the list of active gateways. For local gateways, just stops the gateway.
        Stopping the gateway also cancels its ping task.

        :param gateway: Gateway to be stopped.
        :type gateway: class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        if isinstance(gateway, GatewayRemote):
            logger.info(f"Closing connection for gateway {gateway.id}")
            await asyncio.to_thread(gateway.stop)
            gateway.close()
            self.ping_task_stop(gateway)
            self.remove_gateway(gateway)
        elif isinstance(gateway, GatewayLocal):
            logger.warning(f"Stop local gateway {gateway.id}")
            self.ping_task_stop(gateway)
            await asyncio.to_thread(gateway.stop)

    async def disconnection_cb(self, gateway):
        """ Callback for handling gateway disconnections.

        Stops the gateway and, if it is a local gateway, attempts to restart it.

        :param gateway: Disconnected gateway.
        :type gateway: class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        await self.stop_gateway(gateway)

        if isinstance(gateway, GatewayLocal):
            await asyncio.sleep(1.5)
            await asyncio.to_thread(gateway.gw.programmer.hard_reset)
            if gateway.config:
                await asyncio.to_thread(gateway.start, gateway.config)
            gateway.ping_task = utils.periodic_task_delay(self.ping_gateway,
                self.remote_ping_period, 10, gateway)

        logger.debug(f"Active gateways: {self.active} " +
            f"({threading.active_count()} threads)")

    def create_local_gw(self, local_gw):
        """ Creates and starts a local gateway.

        Initializes the gateway configuration, adds gateway to the gateway
        manager, starts the gateway, and sets up a periodic ping task.

        :param local_gw: Local gateway to be created.
        :type local_gw: class:`~ttgateway.gateway.local.GatewayLocal`
        """
        gw_config = Config(self.node_db, local_gw.tasks_config_cb,
            f"{config.TT_DIR}/.seq_number", prov_mode=False,
            config_mode=config.gateway.task_config)
        self.add_gateway(local_gw)
        local_gw.start(gw_config)
        local_gw.ping_task = utils.periodic_task_delay(self.ping_gateway,
            self.remote_ping_period, 10, local_gw)
        logger.info(f"New local gateway {local_gw.id}")
        logger.debug(f"Active gateways: {self.active} " +
            f"({threading.active_count()} threads)")

    def create_remote_gw(self, socket, gw_id, gw_version, gw_platform):
        """ Creates and starts a remote gateway.

        Initializes the gateway configuration, adds gateway to the gateway
        manager, starts the gateway, and sets up a periodic ping task.

        :param socket: Socket connection for the remote gateway.
        :type socket: socket.socket

        :param gw_id: Gateway ID.
        :type gw_id: str

        :param gw_version: Gateway version.
        :type gw_version: str

        :param gw_platform: Gateway platform type.
        :type gw_platform: str
        """
        remote_gw = GatewayRemote(self.server.event_handler, self.node_db,
            gw_id, gw_version, gw_platform, self.config_cb)
        gw_config = Config(self.node_db, remote_gw.tasks_config_cb,
            f"{config.TT_DIR}/.seq_number", prov_mode=False,
            config_mode=config.gateway.task_config)
        self.add_gateway(remote_gw)
        remote_gw.init("cloud", socket)
        remote_gw.start(gw_config)
        remote_gw.ping_task = utils.periodic_task_delay(self.ping_gateway,
            self.remote_ping_period, 10, remote_gw)
        logger.info(f"New remote gateway {remote_gw.id} from " +
            f"{socket.getpeername()}")
        logger.debug(f"Active gateways: {self.active} " +
            f"({threading.active_count()} threads)")

    async def stop_remote_server(self):
        """ Stops the remote server if it is running."""
        if self.remote_server:
            self.remote_server.close()
            await self.remote_server.wait_closed()

    async def start_remote_server(self):
        """ Starts the remote server.

        Stops any existing remote server and starts a new one on the configured
        port.
        """
        await self.stop_remote_server()
        self.remote_server = await asyncio.start_server(self.remote_server_cb,
            port=self.server_port)
        addr = self.remote_server.sockets[0].getsockname()
        logger.info(f"Remote server on {addr}")

    async def remote_server_cb(self, reader, writer):
        """ Callback for handling new connections to the remote server.

        Performs the handshake process, and if successful, creates a remote
        gateway.

        :param reader: Stream reader.
        :type reader: StreamReader

        :param writer: Stream writer.
        :type writer: StreamWriter
        """
        socket = writer.get_extra_info("socket").dup()
        socket.setblocking(True)
        writer.close()
        await writer.wait_closed()
        if self.tls:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.options |= ssl.OP_NO_SSLv2
            ssl_context.options |= ssl.OP_NO_SSLv3
            ssl_context.options |= ssl.OP_NO_TLSv1
            ssl_context.options |= ssl.OP_NO_TLSv1_1
            ssl_context.options |= ssl.OP_SINGLE_DH_USE
            ssl_context.options |= ssl.OP_SINGLE_ECDH_USE
            ssl_context.load_cert_chain(self.server_cert, self.server_key)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.load_verify_locations(self.ca_cert)
            socket = await asyncio.to_thread(ssl_context.wrap_socket, socket,
                server_side=True)
        gw_data = await asyncio.to_thread(self.handle_handshake, socket)
        if gw_data is None:
            socket.close()
        else:
            logger.debug("Handshake success")
            gw_id = gw_data["id"]
            gw_version = gw_data["version"]
            gw_platform = gw_data["type"]
            self.create_remote_gw(socket, gw_id, gw_version, gw_platform)

    def handle_handshake(self, socket):
        """ Handles the handshake process with a gateway.

        Reads data from the socket until a valid JSON is received or a timeout
        occurs. If the handshake is successful, returns the gateway data.

        :param socket: Socket connection.
        :type socket: socket.socket

        :return: Gateway data if successful, otherwise None.
        :rtype: dict or None
        """
        # TODO read data until timeout or correct json is received.
        try:
            rx = socket.recv(4096)
            if not rx:
                logger.warning("Handshake recieve error")
                return None
            logger.log(9, f"RX msg: {rx}")
        except socket.timeout:
            logger.warning("Handshake timeout")
            return None

        try:
            gw_data = json.loads(rx)
        except ValueError:
            logger.warning("RX data is not a valid JSON")
            return None

        if not "id" in gw_data:
            logger.warning("RX data does not contain valid ID")
            return None

        rsp = {"status": "success"}
        tx = json.dumps(rsp)
        socket.send(tx.encode("utf-8"))

        return gw_data

    def get_gateway_by_node(self, node):
        """ Retrieves the gateway associated with a specific node.

        :param node: Node for which to find the associated gateway.
        :type node: class:`~ttgwlib.node.Node`

        :return: Associated gateway if found, otherwise None.
        :rtype: None or class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        for gateway in self.gateways:
            if gateway.gw.is_node_in_whitelist(node):
                return gateway
        return None

    def get_gateway_by_id(self, gw_id):
        """ Retrieves a gateway by its ID.

        :param gw_id: Gateway ID.
        :type gw_id: str

        :return: Gateway with the specified ID if found, otherwise None.
        :rtype: None or class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        for gateway in self.gateways:
            if gateway.id == gw_id:
                return gateway
        return None

    def get_gateway_by_gw(self, gw):
        """ Retrieves a gateway by its gateway library instance.

        :param gw: Gateway object.
        :type gw: class:`~ttgwlib.gateway.Gateway`

        :return: Gateway matching the gw object if found, otherwise None.
        :rtype: None or class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`
        """
        for gateway in self.gateways:
            if gateway.gw == gw:
                return gateway
        return None

    def event_filter(self, event):
        """ Filters events based on gateway and node whitelist status.

        Updates node coverage data and handles reassignment if necessary.

        :param event: Event to be filtered.
        :type event: class:`~ttgateway.events.Event`

        :return: True if the event is valid and not filtered, otherwise False.
        :rtype: bool
        """
        if not self.event_is_filterable(event):
            return True
        gateway = self.get_gateway_by_gw(event.gw)
        mac = event.node.mac.hex()
        rssi = event.data["rssi"]
        # Node is in event gateway's whitelist
        if event.gw.is_node_in_whitelist(event.node):
            self.node_data.update_coverage(mac, gateway.id, rssi, True)
            self.wl_manager.reassign_cancel(event)
            self.replay_cache_update(event)
            return True
        # Node is not in event gateway's whitelist
        self.node_data.update_coverage(mac, gateway.id, rssi, False)
        for gateway in self.gateways:
            # Node is in any gateway's whitelist
            if gateway.gw.is_node_in_whitelist(event.node):
                # Node is busy
                if gateway.ota_in_progress or gateway.copy_ota_in_progress:
                    return False
                # Event is not cached
                if not self.replay_cache_is_repeated(event):
                    self.wl_manager.reassign_node(event, gateway)
                return False
        self.wl_manager.update_candidate(event)
        return False

    def event_is_filterable(self, event):
        """ Checks if an event is filterable based on its attributes.

        :param event: Event to check.
        :type event: class:`~ttgateway.events.Event`

        :return: True if the event is filterable, otherwise False.
        :rtype: bool
        """
        return (hasattr(event, "node") and event.node and hasattr(event, "gw")
            and event.gw and "rssi" in event.data and "ttl" in event.data and
            "sequence_number" in event.data)

    def replay_cache_update(self, event):
        """ Updates the replay cache with the event's sequence number.

        :param event: Event to update the cache with.
        :type event: class:`~ttgateway.events.Event`
        """
        self.replay_cache[event.node] = event.data["sequence_number"]

    def replay_cache_is_repeated(self, event):
        """Checks if an event's sequence number is repeated in the replay cache.

        :param event: Event to check.
        :type event: class:`~ttgateway.events.Event`

        :return: True if the event's sequence number is repeated,
            otherwise False.
        :rtype: bool
        """
        return event.data["sequence_number"] <= self.replay_cache[event.node]

    # Temporary workaround to maintain backwards compatibility
    def get_main_gateway(self):
        """Retrieves the main gateway, typically a local gateway.

        :return: Main local gateway if found, otherwise None.
        :rtype: class:`~ttgateway.gateway.local.GatewayLocal` or None
        """
        main_gw = None
        for gateway in self.gateways:
            if isinstance(gateway, GatewayLocal):
                main_gw = gateway
                break
        return main_gw

    def config_cb(self, gateway, node):
        """ Callback for configuring a node during the configuring process.

        If automation is enabled and the node is an automation node with
        failsafe configured, sets the failsafe output for the node.

        :param gateway: Gateway to configure.
        :type gateway: class:`~ttgateway.gateway.remote.GatewayRemote` or
            class:`~ttgateway.gateway.local.GatewayLocal`

        :param node: Node to configure.
        :type node: class:`~ttgwlib.node.Node`
        """
        automation = self.server.app_manager.interfaces["automation"]
        if (automation.enabled and node.is_automation() and
                node.mac.hex() in automation.failsafes):
            logger.debug(f"Setting failsafe {node.mac.hex()}")
            relay = automation.get_failsafe_relay1(node)
            dac = automation.get_failsafe_dac1(node)
            def _set_failsafe(task):
                task.gateway.gw.set_failsafe_output(task.node, relay, dac)
            task = GatewayTask(self, node, _set_failsafe)
            self.task_schedule(task)

    async def gateway_mngr_init_cmd(self, command):
        """ Initializes the gateway manager triggered by a command.

        Checks if the gateway manager is already started, otherwise initializes
        it with the specified configuration.

        :param command: Command to initialize the gateway manager.
        :type command: class:`~ttgateway.commands.Command`

        :return: Command response indicating success or failure.
        :rtype: class:`~ttgateway.commands.Response`
        """
        gw_mngr_config = GatewayManagerConfig(self.role, self.server_host)
        if self.started:
            return command.response("Gateway manager already started", False)
        await self.gateway_mngr_init(gw_mngr_config)
        if not self.started:
            return command.response("Unable to start gateway manager", False)
        return command.response(f"{self.role} mode started succesfully")

    async def gateway_mngr_init(self, gw_mngr_config: GatewayManagerConfig):
        """ Initializes the gateway manager with the specified configuration.
        `gateway_mngr_check` should be called before initializing the gateway
        manager.

        For passthrough role, it initializes the first local gateway in
        passthrough mode. The gateway will forward all packets to the host
        specified in the configuration.

        For server role, it initializes every local gateway in regular mode and
        creates a TCP server that listens to new remote gateways. When a new
        remote gateway connects, it initializes it in regular mode.

        For standalone role, it initializes every local gateway in regular mode.

        :param gw_mngr_config: Configuration for the gateway manager.
        :type gw_mngr_config:
            class:`~ttgateway.gateway.gateway_manager.GatewayManagerConfig`
        """
        if gw_mngr_config.role == GatewayRole.PASSTHROUGH:
            self.started = await self.gateway_mngr_init_passthrough(
                gw_mngr_config.address)
        elif gw_mngr_config.role == GatewayRole.SERVER:
            self.started = await self.gateway_mngr_init_server()
        elif gw_mngr_config.role == GatewayRole.STANDALONE:
            self.started = await self.gateway_mngr_init_standalone()
        elif gw_mngr_config.role == GatewayRole.FAULT:
            logger.warning("Fault role enabled. Use fault commands instead")

    async def gateway_mngr_init_passthrough(self, address):
        """ Initializes the gateway manager in passthrough mode.

        Starts the passthrough mode on the first local gateway and pauses the
        application manager.

        :param address: IP address of the host to connect to.
        :type address: str

        :return: True if initialization is successful, otherwise False.
        :rtype: bool
        """
        if len(config.gw_local) == 0:
            return False
        await self.server.app_manager.pause()
        self.passthrough_gw = self.local_gateways[0]
        self.passthrough_gw.start_passthrough(address, self.server_port,
            self.ca_cert, self.client_cert, self.client_key)
        return True

    async def gateway_mngr_init_standalone(self):
        """ Initializes the gateway manager in standalone mode.

        Resumes the application manager, adds event filter, and creates local
        gateways.

        :return: True if initialization is successful, otherwise False.
        :rtype: bool
        """
        await self.server.app_manager.resume()
        self.event_handler.add_event_filter(self.event_filter)
        for gateway in self.local_gateways:
            self.create_local_gw(gateway)
        self.server.gateway = self.get_main_gateway()
        return True

    async def gateway_mngr_init_server(self):
        """ Initializes the gateway manager in server mode.

        Initializes the gateway manager in standalone mode and starts the remote
        server.

        :return: True if initialization is successful, otherwise False.
        :rtype: bool
        """
        await self.gateway_mngr_init_standalone()
        await self.start_remote_server()
        return True

    async def gateway_mngr_check(self):
        """ Initializes local gateways and performs a hardware check based on
        the configuration.
        """
        for gw_local in config.gw_local:
            gateway = GatewayLocal(self.server.event_handler,
                self.node_db, config.backend.device_id, self.config_cb)
            gateway.init(config.gateway.platform, gw_local["port"])
            gateway.check()
            self.local_gateways.append(gateway)

    async def gateway_mngr_uninit_cmd(self, command):
        """ Stops the gateway manager triggered by a command.

        Checks if the gateway manager is already stopped, otherwise stops it.

        :param command: Command to stop the gateway manager.
        :type command: class:`~ttgateway.commands.Command`

        :return: Command response indicating success or failure.
        :rtype: class:`~ttgateway.commands.Response`
        """
        if not self.started:
            return command.response("Gateway manager already stopped", False)
        await self.gateway_mngr_stop()
        if self.started:
            return command.response("Unable to stop gateway manager", False)
        return command.response("Gateway manager stopped succesfully")

    async def gateway_mngr_stop(self):
        """ Stops the gateway manager.

        Stops the remote server, all gateways, and the passthrough mode if
        active. Resets the gateway manager's state.
        """
        if not self.started:
            return
        # Remote server mode
        await self.stop_remote_server()
        self.remote_server = None
        # Stop gateways
        self.event_handler.remove_event_filter()
        self.server.gateway = None
        for gateway in self.gateways[:]:
            await asyncio.to_thread(gateway.stop)
            self.ping_task_stop(gateway)
            self.remove_gateway(gateway)
            if isinstance(gateway, GatewayRemote):
                gateway.close()
        # Passthrough mode
        if self.passthrough_gw:
            await asyncio.to_thread(self.passthrough_gw.stop_passthrough)
            self.passthrough_gw = None
        self.id_count = 0
        self.active = 0
        self.gateways = []
        self.started = False

    def gateway_mngr_list(self, command):
        """ List gateway manager details."""
        if not self.started:
            return command.response("GW manager not initialized", False)
        data = {
            "role": str(self.role),
            "remote_host": self.server_host,
            "server_port": self.server_port,
            "remote_ping_period": self.remote_ping_period,
            "active_gw": self.active,
            "id_count": self.id_count,
            "gw_local": [],
            "gw_remote": []
        }
        for gateway in self.gateways:
            if isinstance(gateway, GatewayLocal):
                whitelist = []
                for node in gateway.gw.get_whitelist_nodes():
                    whitelist.append(node.mac.hex())
                gw_local = {
                    "id": gateway.id,
                    "port": gateway.gw.uart.port,
                    "ping_last_ts": gateway.ping_last_ts,
                    "whitelist": whitelist
                }
                data["gw_local"].append(gw_local)
            elif isinstance(gateway, GatewayRemote):
                try:
                    host, port = gateway.gw.uart.socket.getpeername()
                except OSError:
                    host, port = "Unknown", "Unknown"
                whitelist = []
                for node in gateway.gw.get_whitelist_nodes():
                    whitelist.append(node.mac.hex())
                gw_remote = {
                    "id": gateway.id,
                    "host": host,
                    "port": port,
                    "platform": gateway.platform,
                    "ping_last_ts": gateway.ping_last_ts,
                    "whitelist": whitelist
                }
                data["gw_remote"].append(gw_remote)
        return command.response(f"{self.active} gateways",
            extra_data={"data": data})

    def gateway_mngr_check_pt_connection(self, command):
        """ Check passthrough connection status."""
        if self.role != "passthrough" or self.passthrough_gw is None:
            return command.response("Passthrough not configured",
                extra_data={"status": int(False)})
        connected = self.passthrough_gw.is_passthrough_connected()
        return command.response("Passthrough connection check",
            extra_data={"status": int(connected)})

    def node_list(self, command):
        """ List all nodes."""
        if command.tasks and not self.gateways:
            return command.response("Not available gateways", False)
        nodes = []
        if command.nodes:
            for mac in command.nodes:
                node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
                if node:
                    nodes.append(node)
                else:
                    logger.debug(f"Node {mac} not in database")
        else:
            nodes.extend(self.node_db.get_nodes())
        node_list = []
        for node in nodes:
            if command.last:
                delta = int(dt.now().timestamp()) - node.msg_timestamp
                if delta > command.last:
                    continue
            mac = node.mac.hex()
            pending_tasks = []
            gateway = self.get_gateway_by_node(node)
            if gateway and gateway.is_started():
                pending_tasks = gateway.gw.get_pending_tasks(node)
            data = {
                "mac": mac,
                "addr": node.unicast_addr,
                "uuid": node.uuid.hex(),
                "board_id": node.board_id,
                "pending_tasks": pending_tasks,
                "sleep_period": node.sleep_period,
                "last_wake_ts": node.sleep_timestamp,
                "last_msg_ts": node.msg_timestamp
            }
            data.update(self.node_data.get_data(mac, command.tel,
                command.co2, command.iaq, command.bat, command.ota,
                command.stats, command.pwmt, command.cvg))
            if gateway and command.tasks:
                configured_tasks = gateway.gw.get_configured_tasks(node)
                if configured_tasks is not None:
                    data.update(configured_tasks)
            node_list.append(data)
        return command.response(f"{len(node_list)} nodes",
            extra_data={"node_list": node_list})

    def node_summary(self, command):
        """ Summarize node statistics."""
        data = {}
        nodes_active = 0
        now  = int(dt.now().timestamp())
        nodes = self.node_db.get_nodes()
        for node in nodes:
            delta = now - node.msg_timestamp
            if delta <= 3600:
                nodes_active += 1
        data["nodes_number"] = len(nodes)
        data["nodes_active"] = nodes_active
        if len(nodes) > 0:
            perct_active = (nodes_active * 100) / len(nodes)
            data["perct_active"] = round(perct_active, 2)
        else:
            data["perct_active"] = None
        data.update(self.node_data.get_summary())
        return command.response(extra_data={"node_summary": data})

    def node_cancel_tasks(self, command):
        """ Cancel tasks for specified nodes."""
        def _node_cancel_tasks(task):
            task.gateway.gw.cancel_tasks(task.node)
        for mac in command.nodes:
            node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
            task = GatewayTask(self, node, _node_cancel_tasks)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_reset(self, command):
        """ Reset specified nodes."""
        def _node_reset(task):
            task.gateway.gw.reset_node(task.node)
        for mac in command.nodes:
            node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
            task = GatewayTask(self, node, _node_reset)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_rate(self, command):
        """ Set telemetry rate for specified nodes."""
        def _node_rate(task):
            if config.gateway.task_config == "legacy":
                task.gateway.gw.set_rate_legacy(task.node, command.rate)
            else:
                task.gateway.gw.set_rate(task.node, command.rate)
        for mac in command.nodes:
            node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
            task = GatewayTask(self, node, _node_rate)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_rssi_start(self, command):
        """ Start RSSI measurement for all nodes."""
        if not command.datetime:
            return command.response("Missing datetime param", False)
        event_time = dt.strptime(command.datetime, "%d/%m/%Y %H:%M:%S")
        def _node_rssi_start(task):
            task.gateway.gw.set_task(node=task.node, opcode=8,
                date_event=int(event_time.timestamp()), period=0, task_type=0)
        for node in self.node_db.get_nodes():
            task = GatewayTask(self, node, _node_rssi_start)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_rssi_get(self, command):
        """ Retrieve RSSI status for specified nodes."""
        def _node_rssi_get(task):
            task.gateway.gw.get_status_rssi(task.node)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_rssi_get)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_rssi_ping(self, command):
        """ Ping specified nodes."""
        if not self.gateways:
            return command.response("Not available gateways", False)
        for mac in command.nodes:
            node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
            if not node:
                logger.warning(f"Node {node} not found")
                continue
            self.ping_node(node)
        return command.response()

    def node_accel_off(self, command):
        """ Turn off accelerometer for all nodes."""
        def _node_accel_off(task):
            task.gateway.gw.set_accel(task.node, 0)
        for node in self.node_db.get_nodes():
            task = GatewayTask(self, node, _node_accel_off)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response(result.info, result.success())

    async def node_ota(self, command):
        """ Perform OTA update for nodes."""
        # Check if OTA file is valid
        if not command.ota_zip or not os.path.isfile(command.ota_zip):
            return command.response("OTA data file missing", False)
        # Check if event time is valid
        if not command.datetime:
            return command.response("Event time missing", False)
        # Check if OTA type is valid
        if command.ota_type == "bl":
            ota_type = OtaType.OTA_TYPE_BOOTLOADER
        elif command.ota_type == "app":
            ota_type = OtaType.OTA_TYPE_APPLICATION
        elif command.ota_type == "sd":
            ota_type = OtaType.OTA_TYPE_SOFTDEVICE
        else:
            return command.response("Invalid OTA type", False)
        # Perform OTA
        update_info = []
        update_nodes = []
        update_offset = 300
        event_time = dt.strptime(command.datetime, "%d/%m/%Y %H:%M:%S")
        time_to_update = 10 + (event_time - dt.now()).seconds
        for gateway in self.gateways:
            # Prepare gateway
            gateway.ota_in_progress = True
            gateway.copy_ota_in_progress = True
            logger.debug(f"Gateway {gateway.id}: Copying OTA to flash")
            data = await asyncio.to_thread(gateway.gw.ota_helper.load_ota,
                command.ota_zip, ota_type)
            # Prepare nodes
            if command.nodes:
                target_nodes = []
                for mac in command.nodes:
                    node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
                    target_nodes.append(node)
            else:
                target_nodes = self.node_db.get_nodes()
            nodes = []
            for node in target_nodes:
                if not node or node.board_id != data["board_id"]:
                    continue
                if not gateway.gw.is_node_in_whitelist(node):
                    continue
                if node in update_nodes:
                    continue
                nodes.append(node)
                update_nodes.append(node)
            logger.debug(f"Gateway {gateway.id}: Ready to update " + \
                f"{len(nodes)} nodes with id {data['board_id']}")
            # Program OTA
            if not nodes:
                continue
            asyncio.create_task(gateway.ota_notify_nodes(event_time, nodes,
                data, ota_type))
            asyncio.create_task(gateway.send_ota(time_to_update, nodes))
            # Logs
            gw_update_status = f"Gateway {gateway.id}: Scheduled OTA in " + \
                f"{timedelta(seconds=time_to_update)} " + \
                f"({event_time.strftime('%d/%m/%Y %H:%M:%S')})"
            logger.debug(gw_update_status)
            update_info_gw = {
                "gw_id": gateway.id,
                "event_time": event_time.strftime('%d/%m/%Y %H:%M:%S'),
                "time_to_update": time_to_update,
                "nodes": [str(node) for node in nodes]
            }
            update_info.append(update_info_gw)
            # Update event time
            event_time += timedelta(seconds=update_offset)
            time_to_update += update_offset
        rsp = f"Scheduled OTA in {timedelta(seconds=time_to_update)} " + \
            f"({event_time.strftime('%d/%m/%Y %H:%M:%S')}) for " + \
            f"{len(update_nodes)} nodes"
        return command.response(rsp, extra_data=update_info)

    def node_task_create(self, command):
        """ Schedule task for the specified nodes."""
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        event_time = 0
        if command.datetime:
            event_dt = dt.strptime(command.datetime, "%d/%m/%Y %H:%M:%S")
            event_time = int(event_dt.timestamp())
        period = command.period if command.period else 0
        task_type = command.clock if command.clock else 1
        def _node_task_create(task):
            task.gateway.gw.set_task(task.node, command.opcode, event_time,
                period, task_type)
        for node in nodes:
            task = GatewayTask(self, node, _node_task_create)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_task_delete(self, command):
        """ Delete task for the specified nodes."""
        def _node_task_delete(task):
            task.gateway.gw.delete_task_op(task.node, command.opcode)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_task_delete)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_task_modify(self, command):
        """ Modify task for the specified nodes."""
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        event_time = 0
        if command.datetime:
            event_dt = dt.strptime(command.datetime, "%d/%m/%Y %H:%M:%S")
            event_time = int(event_dt.timestamp())
        period = command.period if command.period else 0
        task_type = command.clock if command.clock else 1
        def _node_task_modify(task):
            task.gateway.gw.change_task(task.node, command.opcode, event_time,
                period, task_type)
        for node in nodes:
            task = GatewayTask(self, node, _node_task_modify)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_tasks_get(self, command):
        """ Get tasks from the specified nodes."""
        def _node_tasks_get(task):
            task.gateway.gw.get_node_tasks(task.node)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_tasks_get)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_ota_status(self, command):
        """ Send ota status request for the specified nodes."""
        def _node_ota_status(task):
            task.gateway.gw.get_node_ota_status(task.node)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_ota_status)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        logger.debug("Send OTA status")
        return command.response()

    def node_beacon_start(self, command):
        """ Start node beaconing the specified nodes."""
        def _node_beacon_start(task):
            task.gateway.gw.start_node_beacon(task.node, command.period_ms)
        for mac in command.nodes:
            node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
            task = GatewayTask(self, node, _node_beacon_start)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_beacon_stop(self, command):
        """ Stop node beaconing the specified nodes."""
        def _node_beacon_stop(task):
            task.gateway.gw.stop_node_beacon(task.node)
        for mac in command.nodes:
            node = self.node_db.get_node_by_mac(bytes.fromhex(mac))
            task = GatewayTask(self, node, _node_beacon_stop)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_set_pwmt_config(self, command):
        """ Set power meter configuration for the specified nodes."""
        def _node_set_pwmt_config(task):
            task.gateway.gw.set_pwmt_conf(task.node, command.phases,
                command.stats, command.values_ph, command.values_tot)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_set_pwmt_config)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_set_pwmt_conv(self, command):
        """ Set power meter conversion factor for the specified nodes."""
        def _node_set_pwmt_conv(task):
            task.gateway.gw.set_pwmt_conv(task.node, command.kv, command.ki)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_set_pwmt_conv)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_temp_mode(self, command):
        """ Set temperature mode for the specified nodes."""
        def _node_temp_mode(task):
            task.gateway.gw.set_temp_mode(task.node, command.mode)
        nodes = []
        if not command.nodes:
            nodes.extend(self.node_db.get_nodes())
        else:
            for mac in command.nodes:
                nodes.append(self.node_db.get_node_by_mac(bytes.fromhex(mac)))
        for node in nodes:
            task = GatewayTask(self, node, _node_temp_mode)
            result = self.task_schedule(task)
            if not result.success():
                logger.warning(result.info)
        return command.response()

    def node_calibrate(self, command):
        """ Set calibration offsets for the specified node."""
        def _node_calibrate(task):
            task.gateway.gw.set_calibration(task.node, command.temp_offset,
                command.humd_offset, command.press_offset)
        node = self.node_db.get_node_by_mac(bytes.fromhex(command.node))
        task = GatewayTask(self, node, _node_calibrate)
        result = self.task_schedule(task)
        return command.response(result.info, result.success())

    def node_reset_calibration(self, command):
        """ Reset calibration offsets for the specified node."""
        def _node_reset_calibration(task):
            task.gateway.gw.reset_calibration(task.node, command.temp,
                command.humd, command.press)
        node = self.node_db.get_node_by_mac(bytes.fromhex(command.node))
        task = GatewayTask(self, node, _node_reset_calibration)
        result = self.task_schedule(task)
        return command.response(result.info, result.success())

    def node_set_dac(self, command):
        """ Set DAC value for the specified node."""
        def _node_set_dac(task):
            task.gateway.gw.set_dac_output(task.node, command.value)
        node = self.node_db.get_node_by_mac(bytes.fromhex(command.node))
        task = GatewayTask(self, node, _node_set_dac)
        result = self.task_schedule(task)
        return command.response(result.info, result.success())

    def node_set_relay(self, command):
        """ Set relay value for the specified node."""
        def _node_set_relay(task):
            task.gateway.gw.set_relay_output(task.node, command.status)
        node = self.node_db.get_node_by_mac(bytes.fromhex(command.node))
        task = GatewayTask(self, node, _node_set_relay)
        result = self.task_schedule(task)
        return command.response(result.info, result.success())

    def node_set_failsafe(self, command):
        """ Set failsafe mode for the specified node."""
        def _node_set_failsafe(task):
            task.gateway.gw.set_failsafe_output(task.node, command.relay,
                command.dac)
        node = self.node_db.get_node_by_mac(bytes.fromhex(command.node))
        task = GatewayTask(self, node, _node_set_failsafe)
        result = self.task_schedule(task)
        return command.response(result.info, result.success())

    def node_send_out_vector(self, command):
        """ Send vector command for the specified node."""
        if not self.server.app_manager.interfaces["automation"].enabled:
            return command.response("Automation app is disabled", False)
        if not self.gateways:
            return command.response("Not available gateways", False)
        if not command.path:
            return command.response("Missing JSON file path", False)
        try:
            with open(command.path) as f:
                cmd_vectors = json.load(f)
        except FileNotFoundError:
            return command.response("Output file not found", False)
        except json.JSONDecodeError:
            return command.response("Invalid JSON file", False)
        rsp = self.server.app_manager.interfaces["automation"].send_vectors(
            cmd_vectors)
        if not rsp:
            return command.response("Send output vector failed", False)
        return command.response()

    def node_output_status(self, command):
        """ Get output status for all automation nodes."""
        if not self.gateways:
            return command.response("Not available gateways", False)
        if not self.server.app_manager.interfaces["automation"].enabled:
            return command.response("Automation app is disabled", False)
        nodes = self.server.app_manager.interfaces["automation"].get_nodes()
        status_nodes = []
        for node, a_node in nodes.items():
            status_node = {
                "mac": node.mac.hex(),
                "status": a_node.status.name,
                "cmd_vector": a_node.out_vector
            }
            status_nodes.append(status_node)
        return command.response(f"{len(status_nodes)} output nodes",
            extra_data={"output_status": status_nodes})

    def node_reboot(self, command):
        """ Reboot node."""
        def _node_reboot(task):
            task.gateway.gw.node_reboot(task.node)
        node = self.node_db.get_node_by_mac(bytes.fromhex(command.node))
        task = GatewayTask(self, node, _node_reboot)
        result = self.task_schedule(task)
        return command.response(result.info, result.success())

    async def dispatch(self, command) -> cmds.Response:
        """ Execute commands or dispatch them to the appropriate handler. """
        logger.debug(f"Command received: {type(command).__name__}")

        for cmd_type, func in self.cmd_handlers.items():
            if isinstance(command, cmd_type):
                if asyncio.iscoroutinefunction(func):
                    return await func(command)
                return func(command)

        if isinstance(command, cmds.GatewayCommand):
            gateway = None
            if command.gw_id:
                gateway = self.get_gateway_by_id(command.gw_id)
            else:
                gateway = self.get_main_gateway()
            if not gateway:
                return command.response("Invalid or unavailable gateway", False)
            resp = await gateway.dispatch(command)
            return resp

        logger.warning(f"Unknown command {type(command)}")
        return command.response("Unknown command", False)
