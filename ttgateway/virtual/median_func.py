from ttgwlib import EventType as LibEventType

from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction
from ttgateway.virtual.virtual_node import VirtualNode


class MedianEvent(Event):
    def __init__(self, node, median_val, _type):
        super().__init__(EventType.VIRTUAL_MEDIAN)
        self.node = node
        self.data = {}
        self.data["median"] = median_val
        self.data["type"] = _type


class MedianFunction(BaseFunction):
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

    async def send_median(self):
        med_val = 0
        if self.type == "temp" and len(self.temp):
            med_val = sorted(list(self.temp.values()))[len(self.temp)//2]
        elif self.type == "hum" and len(self.hum):
            med_val = sorted(list(self.hum.values()))[len(self.hum)//2]
        elif self.type == "press" and len(self.press):
            med_val = sorted(list(self.press.values()))[len(self.press)//2]
        else:
            return # No available data
        await self.send_event(MedianEvent(self.node, med_val, self.type))

    async def run(self):
        self.task = utils.periodic_task(self.send_median, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "sensor_list": list(self.macs),
        }
