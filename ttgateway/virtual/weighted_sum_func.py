import logging

from ttgwlib import EventType as LibEventType

from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction
from ttgateway.virtual.virtual_node import VirtualNode


logger = logging.getLogger(__name__)


class WeightedSumEvent(Event):
    def __init__(self, node, weighted_sum, _type):
        super().__init__(EventType.VIRTUAL_WEIGHTED_SUM)
        self.node = node
        self.data = {}
        self.data["weighted_sum"] = weighted_sum
        self.data["type"] = _type


class WeightedSumFunction(BaseFunction):
    def __init__(self, event_handler, node, _type: str, weights: dict,
            period: int):
        self.node = node
        self.type = _type
        self.weights = weights # List[Dict[mac, weight]]
        self.weights_dict = {}  # Dict[mac, weight]
        for weight in weights:
            self.weights_dict[weight["mac"]] = weight["weight"]
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
                event.node.mac.hex() in self.weights_dict):
            if self.type == "temp":
                self.temp[event.node.mac.hex()] = event.data["temp"]
            elif self.type == "hum":
                self.hum[event.node.mac.hex()] = event.data["hum"]
            elif self.type == "press":
                self.press[event.node.mac.hex()] = event.data["press"]

    async def send_weighted_sum(self):
        weighted_sum = 0
        weight_total = 0
        if self.type == "temp":
            for mac, temp in self.temp.items():
                if mac in self.weights_dict:
                    weighted_sum += self.weights_dict[mac] * temp
                    weight_total += self.weights_dict[mac]
        elif self.type == "hum":
            for mac, hum in self.hum.items():
                if mac in self.weights_dict:
                    weighted_sum += self.weights_dict[mac] * hum
                    weight_total += self.weights_dict[mac]
        elif self.type == "press":
            for mac, press in self.press.items():
                if mac in self.weights_dict:
                    weighted_sum += self.weights_dict[mac] * press
                    weight_total += self.weights_dict[mac]
        if weighted_sum == 0:
            return # No available data
        weighted_avg = weighted_sum / weight_total
        await self.send_event(WeightedSumEvent(self.node, weighted_avg,
                self.type))

    async def run(self):
        self.task = utils.periodic_task(self.send_weighted_sum, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "sensor_list": self.weights,
        }
