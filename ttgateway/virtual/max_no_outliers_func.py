from ttgwlib import EventType as LibEventType

from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction
from ttgateway.virtual.virtual_node import VirtualNode


class MaxNoOutliersEvent(Event):
    def __init__(self, node, max_val, _type):
        super().__init__(EventType.VIRTUAL_MAX_NO_OUTLIERS)
        self.node = node
        self.data = {}
        self.data["max_no_outliers"] = max_val
        self.data["type"] = _type

class MaxNoOutliersFunction(BaseFunction):
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

    def max_no_outliers(self, data_list):
        q1,q3 = utils.percentile(data_list, 25),utils.percentile(data_list, 75)
        iqr = q3 - q1
        upper_outliers = q3 + (1.5 * iqr)
        data_no_outl = [x for x in data_list if x <= upper_outliers]
        max_val = max(data_no_outl)
        return max_val

    async def send_max_no_outliers(self):
        max_val = 0
        if self.type == "temp" and len(self.temp):
            max_val = self.max_no_outliers(self.temp.values())
        elif self.type == "hum" and len(self.hum):
            max_val = self.max_no_outliers(self.hum.values())
        elif self.type == "press" and len(self.press):
            max_val = self.max_no_outliers(self.press.values())
        else:
            return # No available data
        await self.send_event(MaxNoOutliersEvent(self.node, max_val, self.type))

    async def run(self):
        self.task = utils.periodic_task(self.send_max_no_outliers, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "sensor_list": list(self.macs),
        }
