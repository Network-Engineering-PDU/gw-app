import asyncio
import logging

from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction


logger = logging.getLogger(__name__)


class SnmpGetEvent(Event):
    def __init__(self, node, snmp_data, _type, extra_params=None):
        super().__init__(EventType.VIRTUAL_SNMP_GET)
        self.node = node
        self.data = {}
        self.data["snmp_data"] = snmp_data
        self.data["type"] = _type
        if extra_params is not None:
            self.data["extra_params"] = extra_params


class SnmpGetFunction(BaseFunction):
    def __init__(self, event_handler, node, _type: str, host: str,
            community: str, version: int, oid: str, period: int,
            snmp_client: "SnmpClient", extra_params: dict=None):
        self.node = node
        self.type = _type
        self.host = host
        self.community = community
        self.version = version
        self.oid = oid
        self.snmp_client = snmp_client
        self.period = int(period)
        self.extra_params = extra_params
        handlers = []
        super().__init__(event_handler, handlers)

    async def send_snmp_get(self):
        if not self.snmp_client.check_oid_input(self.oid):
            logger.error(f"Invalid OID: {self.node.mac.hex()}")
            return
        rsp = await asyncio.to_thread(self.snmp_client.get, self.host,
            self.community, self.oid, self.version)
        if rsp[0] is None:
            logger.error(f"Invalid host or community: {self.node.mac.hex()}")
            return
        if not isinstance(rsp[1], int):
            logger.error(f"Invalid response type: {self.node.mac.hex()}")
            return
        await self.send_event(SnmpGetEvent(self.node, rsp[1], self.type,
            self.extra_params))

    async def run(self):
        self.task = utils.periodic_task(self.send_snmp_get, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "host": self.host,
            "community": self.community,
            "version": self.version,
            "oid": self.oid,
        }
