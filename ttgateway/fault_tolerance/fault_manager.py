import asyncio
import logging

import ttraft
from ttgwlib import EventType as LibEventType

from ttgateway import utils
import ttgateway.commands as cmds
from ttgateway.config import config
from ttgateway.events import EventType
from ttgateway.fault_tolerance.mesh_transport import MeshTransport
from ttgateway.fault_tolerance.udp_transport import UdpTransport
from ttgateway.fault_tolerance.backend_helper import FaultBackendHelper
from ttgateway.gateway.gateway_manager import GatewayManagerConfig, GatewayRole


logger = logging.getLogger(__name__)


class FaultManager:
    """ Manages fault tolerance mechanisms in a gateway.

    FaultManager is responsible for maintaining the network configuration of the
    gateway in backend, downloading the network configuration of every node on
    the cluster, and using the most suitable fault tolerance algorithm depending
    on the number of nodes available in the cluster.

    When the cluster consists of three or more nodes, raft consensous algorithm
    is used. When the cluster contains two nodes, failover algorithm is used. If
    only one node is available, standalone mode is used.
    """
    STDALONE_LEN = 1
    FAILOVER_LEN = 2
    RAFT_MIN_LEN = 3
    INIT_RETRY_S = 30
    def __init__(self, server):
        """ Initializes the FaultManager with a server instance.

        :param server: The server instance used by the fault manager.
        :type server: class:`~ttgateway.server.Server`
        """
        self.server = server
        self.event_handler = server.event_handler
        self.event_handler.add_handler(LibEventType.TEMP_DATA,
            self.telemetry_handler)
        self.event_handler.add_handler(LibEventType.TEMP_DATA_RELIABLE,
            self.telemetry_handler)
        self.event_handler.add_handler(LibEventType.PWMT_DATA,
            self.pwmt_handler)
        self.event_handler.add_handler(EventType.BACKUP_PUT,
            self.backup_put_handler)
        self.backend_helper = FaultBackendHelper(self)
        self.is_started = False
        self.run_task = None
        self.module = None
        self.loop = None
        self.node_id = None
        self.type = None
        self.cluster = []
        self.lock = asyncio.Lock()
        self.raft_config = ttraft.Config(
            persistent_dir=f"{config.TT_DIR}/raft",
            max_log_size=16384,
            follower_timeout=(10, 15), #TODO: move inside transport
            heartbeat_period=4.5,
            serializer="json", #TODO: change to msgpack
            logger=logging.getLogger(),
            on_follower_cb=self.on_follower_cb,
            on_candidate_cb=None,
            on_leader_cb=self.on_leader_cb,
            on_leader_change_cb=self.on_follower_cb
        )

    @property
    def transport(self):
        """ Returns the transport type configured for the fault manager.

        :return: The transport type.
        :rtype: str
        """
        return config.fault_manager.transport

    def start(self):
        """ Starts the fault manager if it is not already started.
        """
        if self.is_started:
            return
        self.is_started = True
        self.loop = asyncio.get_running_loop()
        self.run_task = asyncio.create_task(self.run())

    async def run(self):
        """ The main loop for running the fault manager.

        It first checks if Internet connection is available. Then it uploads the
        gateway network configuration. Then, it downloads the network
        configuration of every node in the cluster. Finally, it starts the
        fault tolerance module.
        """
        first_try = True
        while self.is_started:
            if not first_try:
                await asyncio.sleep(self.INIT_RETRY_S)
            first_try = False
            if not await self.wait_for_internet_connection():
                logger.error("Internet connection failed")
                continue
            if not await self.backend_helper.update_gateway_info():
                logger.error("Unable to upload gateway network to backend")
                continue
            if not await self.backend_helper.get_cluster():
                logger.error("Unable to get cluster from backend")
                continue
            try:
                status = await self.start_module()
            except OSError as exc:
                logger.error(f"OSError: {exc}")
                continue
            if not status:
                logger.error("Unable to init fault module")
            return

    async def start_module(self):
        """ Starts the fault tolerance module based on the cluster
        configuration.

        Depending on the number of nodes in the cluster the fault manager uses
        the most suitable consensous module. For three or more nodes, raft
        consensous algorithm is used; for two nodes, failover algorithm is used;
        for one node, standalone mode is used.

        :return: True if the module was successfully started, False otherwise.
        :rtype: bool
        """
        if self.transport == "bt-mesh":
            transport_instance = MeshTransport(self.server.gateway,
                self.server.event_handler)
        elif self.transport == "udp":
            transport_instance = UdpTransport(self.node_id)
        else:
            raise TypeError("Invalid transport type")

        self.is_started = True
        if len(self.cluster) >= self.RAFT_MIN_LEN:
            self.type = "raft"
            self.module = ttraft.ConsensusModule(self.node_id, self.cluster,
                transport_instance, self.raft_config, self.server.node_db)
            await self.module.start()
        elif len(self.cluster) == self.FAILOVER_LEN:
            self.type = "failover"
            self.module = ttraft.Failover(self.node_id, self.cluster[1],
                transport_instance, self.raft_config, self.server.node_db)
            await self.module.start()
        elif len(self.cluster) == self.STDALONE_LEN:
            self.type = "standalone"
            self.module = None
            gw_mngr_config = GatewayManagerConfig(GatewayRole.STANDALONE, None)
            await self.server.gw_manager.gateway_mngr_stop()
            await self.server.gw_manager.gateway_mngr_init(gw_mngr_config)
        else:
            logger.error("Unable to start fault manager: No gateways available")
            return False
        return True

    async def stop(self):
        """ Stops the fault manager and its associated fault tolerance module
        if it is started.
        """
        if not self.is_started:
            return
        self.is_started = False
        if self.run_task:
            self.run_task.cancel()
        self.type = None
        if self.module:
            await self.module.stop()

    def send(self, command):
        """ Sends a command to the fault tolerance module if it is started.

        :param command: The command to be sent.
        :type command: tuple containing the opcode
            class:`~ttgateway.fault_tolerance.raft_sqlite_database.RaftCmds`
            and a dict with the command data
        """
        if self.is_started and self.module:
            coro = self.module.client_request(command)
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def convert_node_type(self, node):
        """ Converts the node identifier to the appropriate type based on the
        transport layer.
        """
        if self.transport == "bt-mesh":
            return int(node)
        return node

    async def on_follower_cb(self):
        """ Callback for when the gateway becomes a follower.

        Starts passthrough mode.
        """
        logger.debug("Gateway became follower, starting passthrough mode")
        async with self.lock:
            await self.server.gw_manager.gateway_mngr_stop()
            if self.module.current_leader() is None:
                return
            gw_mngr_config = GatewayManagerConfig(GatewayRole.PASSTHROUGH,
                self.module.current_leader())
            await self.server.gw_manager.gateway_mngr_init(gw_mngr_config)

    async def on_leader_cb(self):
        """ Callback for when the gateway becomes a leader.

        Starts server mode.
        """
        logger.debug("Gateway became leader, starting server mode")
        async with self.lock:
            gw_mngr_config = GatewayManagerConfig(GatewayRole.SERVER,
                self.module.current_leader())
            await self.server.gw_manager.gateway_mngr_stop()
            await self.server.gw_manager.gateway_mngr_init(gw_mngr_config)

    async def cluster_update_cb(self, old_cluster, new_cluster):
        """ Callback for when the cluster is updated.

        Restarts the fault manager if the cluster changes.

        :param old_cluster: The previous cluster configuration.
        :type old_cluster: List[str]

        :param new_cluster: The new cluster configuration.
        :type new_cluster: List[str]
        """
        if sorted(old_cluster) == sorted(new_cluster):
            return
        await self.stop()
        self.start()

    async def wait_for_internet_connection(self):
        """ Waits for an internet connection to be available.

        :return: True if an internet connection is established, False otherwise.
        :rtype: bool
        """
        retries = 60
        while not utils.check_internet_connection():
            if retries == 0:
                return False
            asyncio.sleep(2)
            retries -= 1
        return True

    async def process_command(self, command):
        """ Processes incoming commands related to the fault manager.

        :param command: The command to be processed.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response to the command.
        :rtype: class:`~ttgateway.commands.Response`
        """
        logger.debug(f"Command received: {type(command).__name__}")

        if isinstance(command, cmds.FaultStatus):
            if not self.is_started:
                return command.response("Fault module is not started", False)
            data = {
                "status": self.is_started,
                "strategy": self.type,
                "transport": self.transport,
                "state": None,
                "cluster": None,
                "leader": None,

            }
            if self.module is not None:
                data["state"] = type(self.module.state).__name__
                if self.type == "failover":
                    data["cluster"] = [self.module.node_id, self.module.peer_id]
                if self.type == "raft":
                    data["cluster"] = self.module.cluster
                data["leader"] = self.module.current_leader()
            return command.response(extra_data=data)

        if isinstance(command, cmds.FaultEnable):
            if self.is_started:
                return command.response("Fault module already started", False)
            try:
                self.start()
            except TypeError:
                return command.response("Invalid transport, check config")
            return command.response()

        if isinstance(command, cmds.FaultDisable):
            if not self.is_started:
                return command.response("Fault module is not running", False)
            await self.stop()
            return command.response()

        if isinstance(command, cmds.FaultListNodes):
            if not self.is_started:
                return command.response("Fault manager not started", False)
            node_list = list(self.cluster)
            return command.response(extra_data={"node_list": node_list})

        if isinstance(command, cmds.FaultTest):
            if not self.is_started:
                return command.response("Fault module is not started", False)
            if not self.module.is_leader():
                return command.response("Node is not leader", False)
            await self.module.client_request(command.cmd)
            return command.response()

        if isinstance(command, cmds.FaultNewCluster):
            if not self.is_started:
                return command.response("Fault module is not started", False)
            if not self.module.is_leader():
                return command.response("Node is not leader", False)
            await self.module.client_new_cluster(command.cluster)
            return command.response()

        if isinstance(command, cmds.FaultGetCluster):
            if not self.is_started:
                return command.response("Fault module is not started", False)
            old_cluster = self.cluster
            status = await self.backend_helper.get_cluster()
            if not status:
                return command.response("Cluster could not be get", False)
            logger.info(f"Updated cluster: {self.cluster}")
            await self.cluster_update_cb(old_cluster, self.cluster)
            return command.response()

        logger.warning("Unknown command")
        return command.response("Unknown command", False)

    def telemetry_handler(self, event):
        """ Handles telemetry events and updates the node database.

        :param event: The telemetry event.
        :type event: class:`~ttgateway.events.Event`
        """
        if not self.module or not self.module.is_leader():
            return
        self.server.node_db.update_telemetry(event)

    def pwmt_handler(self, event):
        """ Handles PWMT events and updates the node database.

        :param event: The PWMT event.
        :type event: class:`~ttgateway.events.Event`
        """
        if not self.module or not self.module.is_leader():
            return
        self.server.node_db.update_pwmt(event)

    def backup_put_handler(self, event):
        """ Handles backup put events and saves the backup to the node database.

        :param event: The backup put event.
        :type event: class:`~ttgateway.events.Event`
        """
        if not self.module or not self.module.is_leader():
            return
        self.server.node_db.save_backup(event)
