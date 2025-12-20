from ttgwlib import EventType as LibEventType

from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction
from ttgateway.virtual.virtual_node import VirtualNode


class MinEvent(Event):
    def __init__(self, node, min_val, _type):
        super().__init__(EventType.VIRTUAL_MIN)
        self.node = node
        self.data = {}
        self.data["min"] = min_val
        self.data["type"] = _type


class MinimumFunction(BaseFunction):
    def __init__(self, event_handler, node, _type: str, macs: list,
            period: int):
        self.node = node
        self.type = _type
        self.macs = macs
        self.period = int(period)
        handlers = [
            (LibEventType.TEMP_DATA, self.telemetry_handler),
            (LibEventType.TEMP_DATA_RELIABLE, self.telemetry_handler),
        ]
        self.temp = {}
        self.hum = {}
        self.press = {}
        self.power = {} # TODO: add power handler
        super().__init__(event_handler, handlers)

    def telemetry_handler(self, event):
        if (not isinstance(event.node, VirtualNode) and
                event.node.mac.hex() in self.macs):
            if self.type == "temp":
                self.temp[event.node.mac.hex()] = event.data["temp"]
            elif self.type == "hum":
                self.hum[event.node.mac.hex()] = event.data["hum"]
            elif self.type == "press":
                self.press[event.node.mac.hex()] = event.data["press"]

    async def send_min(self):
        min_val = 0
        if self.type == "temp" and len(self.temp):
            min_val = min(self.temp.values())
        elif self.type == "hum" and len(self.hum):
            min_val = min(self.hum.values())
        elif self.type == "press" and len(self.press):
            min_val = min(self.press.values())
        else:
            return # No available data
        await self.send_event(MinEvent(self.node, min_val, self.type))

    async def run(self):
        self.task = utils.periodic_task(self.send_min, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "sensor_list": list(self.macs),
        }
