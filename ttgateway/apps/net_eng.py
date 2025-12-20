from datetime import datetime as dt

from ttgwlib import EventType

from ttgateway import utils
from ttgateway.http_helper import HttpHelper


class NetworkEngineeringApp:
    NE_URL = "http://localhost"
    NE_PORT = 80
    BASE_URL = f"{NE_URL}:{NE_PORT}/"
    SENSOR_DATA_URL = f"{BASE_URL}api/sensors-data/"
    SENSOR_NEW_URL = f"{BASE_URL}api/sensors-new/"
    PERIOD = 60

    def __init__(self, node_db):
        self.node_db = node_db
        self.http = HttpHelper()
        self.task = None
        self.data = {}
        self.handlers = [
            (EventType.TEMP_DATA, self.telemetry_handler),
            (EventType.TEMP_DATA_RELIABLE, self.telemetry_handler),
            (EventType.BAT_DATA, self.battery_handler),
            (EventType.PROV_COMPLETE, self.prov_complete_handler),
            (EventType.PROV_LINK_CLOSED, self.prov_link_closed_handler),
        ]
        self.new_node_devkey = None # ProvComplete only gives DevKey, which is
                                    # used to get the new node

    async def enable(self):
        if not self.task:
            self.task = utils.periodic_task(self.send_data, self.PERIOD)
        return True

    async def disable(self):
        if self.task:
            self.task.cancel()
            self.task = None
        return True

    def create_node_entry(self, mac: bytes):
        self.data[mac] = {
            "mac_address": mac.hex(),
            "datetime": dt.utcnow().strftime("%d/%m/%Y %H:%M"),
            "temperature": 0,
            "humidity": 0,
            "pressure": 0,
            "rssi": 0,
            "battery": 0,
        }

    def telemetry_handler(self, event):
        if event.node.mac not in self.data:
            self.create_node_entry(event.node.mac)
        self.data[event.node.mac].update({
            "datetime": dt.utcnow().strftime("%d/%m/%Y %H:%M"),
            "temperature": event.data["temp"],
            "humidity": event.data["hum"],
            "pressure": event.data["press"],
            "rssi": event.data["rssi"],
        })

    def battery_handler(self, event):
        if event.node.mac not in self.data:
            self.create_node_entry(event.node.mac)
        self.data[event.node.mac]["battery"] = event.data["bat"]

    async def send_data(self):
        if not self.data:
            return
        body = {"data": list(self.data.values())}
        self.data.clear()
        await self.http.request("ne_data", "POST", self.SENSOR_DATA_URL, body)

    def prov_complete_handler(self, event):
        """ The PROV_COMPLETE event only gives the new node devkey, not the
        node object itself, so it will be used to iterate over the stored
        nodes to find the new one.
        It's not done in this handler because gw-library uses this same
        event to store the node in the database, and it is not known which
        handler will run first (race condition). So in this event we just
        store the devkey, and in the PROV_LINK_CLOSED event, which always
        happens afterwards, the node is actually found and sent to the NE
        backend.
        """
        self.new_node_devkey = event.data["device_key"]

    async def prov_link_closed_handler(self, event):
        if self.new_node_devkey is not None:
            for node in self.node_db.get_nodes():
                if node.devkey == self.new_node_devkey:
                    body = {"mac_address": node.mac.hex()}
                    await self.http.request("ne_sensor", "POST",
                        self.SENSOR_NEW_URL, body)
                    return
        self.new_node_devkey = None
