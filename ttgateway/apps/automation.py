import logging
from enum import Enum

from ttgwlib import EventType

from ttgateway import utils
from ttgateway.http_helper import HttpHelper
from ttgateway.config import config
from ttgateway.gateway.gateway_manager import GatewayTask, GatewayTaskStatus


logger = logging.getLogger(__name__)


class AutomationStatus(Enum):
    SUCCESS = 0
    SENDING = 1
    ERROR = 2


class AutomationNode:
    def __init__(self):
        self.out_vector = None
        self.vector_idx = 0
        self.retries = 0
        self.status = None

    def error(self):
        self.retries = 0
        self.status = AutomationStatus.ERROR
        self.out_vector = None


class AutomationApp:
    MAX_RETRIES = 3
    MAX_VECTOR_LEN = 120
    INIT_DELAY = 30
    def __init__(self, server):
        self.server = server
        self.http = HttpHelper(self.url, self.user, self.password)
        self.get_vectors_task = None
        self.status_task = None
        self.enabled = False
        self.nodes = {}
        self.failsafes = {}
        self.handlers = [
            (EventType.OUTPUT_CMD_ACK, self.cmd_ack_handler),
            (EventType.OUTPUT_CMD_NACK, self.cmd_nack_handler),
            (EventType.OUTPUT_CMD_ERROR, self.cmd_error_handler),
        ]

    @property
    def url(self):
        return config.backend.url

    @property
    def user(self):
        return config.backend.user

    @property
    def password(self):
        return config.backend.password

    @property
    def get_vectors_period(self):
        return config.gateway.automation_get_period

    @property
    def status_period(self):
        return config.gateway.automation_status_period

    async def enable(self):
        if self.enabled:
            return False
        self.enabled = True
        await self.get_failsafes()
        # By checking that it only starts once and knowing that period
        # will always exist, this if statement is unnecessary.
        if not self.get_vectors_task and self.get_vectors_period:
            self.get_vectors_task = utils.periodic_task_delay(self.get_vectors,
                self.get_vectors_period, self.INIT_DELAY)
        if not self.status_task and self.status_period:
            self.status_task = utils.periodic_task_delay(self.send_status,
                self.status_period, self.INIT_DELAY)
        return True

    async def disable(self):
        if not self.enabled:
            return False
        self.enabled = False
        self.failsafes = {}
        if self.get_vectors_task:
            self.get_vectors_task.cancel()
            self.get_vectors_task = None
        if self.status_task:
            self.status_task.cancel()
            self.status_task = None
        return True

    def cmd_ack_handler(self, event):
        if hasattr(event, "node") and event.node is not None:
            node = event.node
        else:
            return
        if not node in self.nodes:
            return
        a_node = self.nodes[node]
        if a_node.status != AutomationStatus.SENDING:
            return
        logger.debug(f"Automation ACK handler. Node {node}, idx: " \
            f"{a_node.vector_idx}, output_vector len: {len(a_node.out_vector)}")
        gateway = self.server.gw_manager.get_gateway_by_node(node)
        if not gateway:
            logger.warning(f"Gateway not found for node {node}")
            a_node.error()
            return
        if not gateway.is_started():
            logger.warning(f"Gateway not initialized for node {node}")
            a_node.error()
            return
        # Stop ACK received successfully
        if a_node.vector_idx > len(a_node.out_vector):
            a_node.status = AutomationStatus.SUCCESS
            a_node.retries = 0
            logger.info(f"Successfully received stop ACK output " \
                f"for node {node}")
            return
        # Last command, sending stop
        if a_node.vector_idx == len(a_node.out_vector):
            gateway.gw.send_stop_output(node)
            logger.info(f"Successfully send stop output for node {node}")
            a_node.vector_idx += 1
            return
        relay = a_node.out_vector[a_node.vector_idx]["relay1"]
        dac = a_node.out_vector[a_node.vector_idx]["dac1"]
        cmd_dt = int(a_node.out_vector[a_node.vector_idx]["dt"])
        gateway.gw.send_cmd_output(node, relay, dac, cmd_dt)
        logger.info(f"Successfully send command output for node {node}")
        a_node.vector_idx += 1

    def cmd_nack_handler(self, event):
        if hasattr(event, "node") and event.node is not None:
            node = event.node
        else:
            return
        if not node in self.nodes:
            return
        a_node = self.nodes[node]
        logger.error(f"NACK. Could not send commands to node {node}")
        a_node.retries += 1
        if a_node.retries == self.MAX_RETRIES:
            a_node.error()
            return
        self.send_vector(node, a_node.out_vector)

    def cmd_error_handler(self, event):
        if hasattr(event, "node") and event.node is not None:
            node = event.node
        else:
            return
        if not node in self.nodes:
            return
        a_node = self.nodes[node]
        logger.error(f"ERROR. Could not send commands to node {node}")
        a_node.retries += 1
        if a_node.retries == self.MAX_RETRIES:
            a_node.error()
            return
        self.send_vector(node, a_node.out_vector)

    def get_nodes(self):
        return self.nodes

    def send_vectors(self, cmd_vectors):
        for mac, cmd_vect in cmd_vectors.items():
            node = self.server.node_db.get_node_by_mac(bytes.fromhex(mac))
            if not node:
                logger.warning(f"Node {mac} not found")
                continue
            if len(cmd_vect) > self.MAX_VECTOR_LEN:
                cmd_vect = cmd_vect[:self.MAX_VECTOR_LEN]
            self.send_vector(node, cmd_vect)
        return True

    def send_vector(self, node, out_vector):
        if not self.enabled:
            logger.warning(f"Can not send start output for node {node}. " \
                f"Automation app is disabled")
            self.nodes[node].error()
            return False
        def _send_vector(task):
            task.gateway.gw.send_start_output(task.node, len(out_vector))
        if not node in self.nodes:
            a_node = AutomationNode()
            self.nodes[node] = a_node
        self.nodes[node].out_vector = out_vector
        self.nodes[node].vector_idx = 0
        self.nodes[node].status = AutomationStatus.SENDING
        task = GatewayTask(self.server.gw_manager, node, _send_vector)
        result = self.server.gw_manager.task_schedule(task)
        if result.status not in (GatewayTaskStatus.SUCCESS,
                GatewayTaskStatus.NO_GW):
            self.nodes[node].error()
            return False
        logger.info(f"Successfully send start output for node {node}")
        return True

    async def get_failsafes(self):
        url = f"{self.url}/automation/failsafe/"
        rsp = await self.http.request("automation_failsafe", "GET",
            url, None, None)
        if rsp is not None and rsp.ok:
            self.failsafes = rsp.json()["data"]
        else:
            logger.error("Unable to get automation failsafes")
            return

    async def get_vectors(self):
        url = f"{self.url}/automation/cmd/"
        rsp = await self.http.request("automation_cmd", "GET", url,
            None, None)
        if rsp is not None and rsp.ok:
            cmds = rsp.json()["data"]
            self.send_vectors(cmds)
        else:
            logger.error("Unable to get automation commands")
            return

    async def send_status(self):
        url = f"{self.url}/automation/sensor-status/"
        sensor_status = {}
        for node in self.nodes:
            sensor_status[node.mac.hex()] = self.nodes[node].status.value
        await self.http.request("automation_status", "POST", url, sensor_status)

    def get_failsafe_relay1(self, node):
        mac = node.mac.hex()
        if mac in self.failsafes:
            return self.failsafes[node.mac.hex()]["relay1"]
        return None

    def get_failsafe_dac1(self, node):
        mac = node.mac.hex()
        if mac in self.failsafes:
            return self.failsafes[node.mac.hex()]["dac1"]
        return None
