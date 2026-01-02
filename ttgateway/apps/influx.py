import time
import asyncio
import logging
from datetime import datetime
import urllib3

from ttgwlib import EventType
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

from ttgateway.config import config

logger = logging.getLogger(__name__)

class InfluxApp:
    def __init__(self):
        self.handlers = [
            (EventType.TEMP_DATA, self.telemetry_handler),
            (EventType.TEMP_DATA_RELIABLE, self.telemetry_handler),
            (EventType.IAQ_DATA, self.iaq_handler),
            (EventType.CO2_DATA, self.co2_handler),
            (EventType.BAT_DATA, self.battery_handler),
            (EventType.PWMT_DATA, self.pwmt_data_handler),
        ]

        self.client = None
        self.write_api = None

    async def enable(self):
        if (not config.influxdb.ip
                or not config.influxdb.token
                or not config.influxdb.org
                or not config.influxdb.bucket_name
                or not config.influxdb.point_name
                or not config.influxdb.tag_name):
            raise ValueError("Invalid InfluxDB configuration")
        self.client = InfluxDBClient(url=f"http://{config.influxdb.ip}:8086",
                token=config.influxdb.token)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

        return True

    async def disable(self):
        self.client = None
        self.write_api = None

        return True

    def write(self, mac, unicast_addr, _type, value, timestamp, rssi):
        point = Point(config.influxdb.point_name)
        point.tag(config.influxdb.tag_name, str(unicast_addr))
        point.field(_type, value)
        point.time(datetime.utcnow(), WritePrecision.NS)

        try:
            self.write_api.write(config.influxdb.bucket_name,
                config.influxdb.org, point)
        except urllib3.connection.NewConnectionError:
            logger.error("Influx connection error")
        except ApiException:
            logger.error("Influx API error")

    async def telemetry_handler(self, event):
        timestamp = int(time.time())
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "TEMP", event.data["temp"],
                timestamp, event.data["rssi"])
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "HUM", event.data["hum"],
                timestamp, event.data["rssi"])
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "PRE", event.data["press"],
                timestamp, event.data["rssi"])

    async def battery_handler(self, event):
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "BAT", event.data["bat"],
                int(time.time()), event.data["rssi"])

    async def iaq_handler(self, event):
        timestamp = int(time.time())
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "IAQ", event.data["iaq"],
                timestamp, event.data["rssi"])
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "TVOC", event.data["tvoc"],
                timestamp, event.data["rssi"])
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "ETOH", event.data["etoh"],
                timestamp, event.data["rssi"])
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "ECO2", event.data["eco2"],
                timestamp, event.data["rssi"])

    async def co2_handler(self, event):
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "CO2", event.data["co2"],
                int(time.time()), event.data["rssi"])

    async def pwmt_data_handler(self, event):
        timestamp = int(time.time())
        calc_status = (event.data["ctl"] >> 6) & 0b11
        # val_type = (event.data["ctl"] >> 4) & 0b11
        msg_id = (event.data["ctl"] >> 2) & 0b11
        ph_id = event.data["ctl"] & 0b11
        ph_str = str(ph_id) if ph_id else "TOTAL"
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "POWER_METER_STATUS", calc_status,
                timestamp, event.data["rssi"])
        if calc_status != 0:
            return
        if ph_id == 0:
            if msg_id == 0:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ACTIVE_POWER_{ph_str}",
                        event.data["p_tot"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"REACTIVE_POWER_{ph_str}",
                        event.data["q_tot"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"APPARENT_POWER_{ph_str}",
                        event.data["s_tot"], timestamp, event.data["rssi"])
            elif msg_id == 1:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, "PHASE12",
                        event.data["ph12"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, "PHASE23",
                        event.data["ph23"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, "PHASE31",
                        event.data["ph31"], timestamp, event.data["rssi"])
            elif msg_id == 2:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, "VOLTAGE12",
                        event.data["v12"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, "VOLTAGE23",
                        event.data["v23"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, "VOLTAGE31",
                        event.data["v31"], timestamp, event.data["rssi"])
            elif msg_id == 3:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ENERGY_{ph_str}",
                        event.data["e_tot"], timestamp, event.data["rssi"])
        else:
            if msg_id == 0:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"VOLTAGE_{ph_str}",
                        event.data["v"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"CURRENT_{ph_str}",
                        event.data["i"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"FREQUENCY_{ph_str}",
                        event.data["f"], timestamp, event.data["rssi"])
            elif msg_id == 1:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ACTIVE_POWER_{ph_str}",
                        event.data["p"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"POWER_FACTOR_{ph_str}",
                        event.data["pf"], timestamp, event.data["rssi"])
            elif msg_id == 2:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"REACTIVE_POWER_{ph_str}",
                        event.data["q"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"APPARENT_POWER_{ph_str}",
                        event.data["s"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"PHASE_{ph_str}",
                        event.data["ph"], timestamp, event.data["rssi"])
            elif msg_id == 3:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ENERGY_{ph_str}",
                        event.data["e"], timestamp, event.data["rssi"])
