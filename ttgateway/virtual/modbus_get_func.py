import asyncio
import logging

from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction


logger = logging.getLogger(__name__)


class ModbusGetEvent(Event):
    def __init__(self, node, modbus_data, _type):
        super().__init__(EventType.VIRTUAL_MODBUS_GET)
        self.node = node
        self.data = {}
        self.data["modbus_data"] = modbus_data
        self.data["type"] = _type


class ModbusGetFunction(BaseFunction):
    def __init__(self, event_handler, node, _type: str, host: str,
            port: int, address: int, slave: int, period: int,
            modbus_client: "ModbusClient"):
        self.node = node
        self.type = _type
        self.host = host
        self.port = port
        self.address = address
        self.slave = slave
        self.modbus_client = modbus_client
        self.period = int(period)
        handlers = []
        super().__init__(event_handler, handlers)

    async def send_modbus_get(self):
        rsp = await asyncio.to_thread(self.modbus_client.read_holding_registers,
            self.host, self.port, self.address, self.slave)
        await self.send_event(ModbusGetEvent(self.node, rsp, self.type))

    async def run(self):
        self.task = utils.periodic_task(self.send_modbus_get, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "host": self.host,
            "port": self.port,
            "address": self.address,
            "slave": self.slave,
        }
