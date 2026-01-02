import time
import asyncio
import logging
import json

from ttgwlib import EventType

import paho.mqtt.client as mqtt

from ttgateway.config import config

logger = logging.getLogger(__name__)

class MQTTApp:
    def __init__(self):
        self.handlers = [
            (EventType.TEMP_DATA, self.telemetry_handler),
            (EventType.TEMP_DATA_RELIABLE, self.telemetry_handler),
            (EventType.IAQ_DATA, self.iaq_handler),
            (EventType.CO2_DATA, self.co2_handler),
            (EventType.BAT_DATA, self.battery_handler),
            (EventType.PWMT_DATA, self.pwmt_data_handler),
        ]

        if not config.mqtt.ip:
            raise ValueError("Invalid MQTT configuration")

        self.nodes = {}

        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    async def enable(self):
        logger.info(f"Try to connect to {config.mqtt.ip}:{config.mqtt.port}")
        self.client.connect_async(f"{config.mqtt.ip}", config.mqtt.port, 60)

        self.client.loop_start()
        return True

    async def disable(self):
        self.client.disconnect()
        self.client.loop_stop()
        return True

    def _on_discovery(self):
        data = {
                "mac": "not_implemented"
            }

        self.client.publish(f"{config.mqtt.prefix}/discover", json.dumps(data))

    def _on_connect(self, client, userdata, flags, rc):
        logger.info(f"Connected with result code {rc}")

        self.client.subscribe(f"{config.mqtt.prefix}/discover/get")

    def _on_message(self, client, userdata, msg):
        logger.info(f"{msg.topic}: {msg.payload}")

        if msg.topic == f"{config.mqtt.prefix}/discover/get":
            self._on_discovery()

    def write(self, mac, unicast_addr, _type, value, timestamp, rssi):
        data = {
                "mac": mac,
                "type": _type,
                "value": value,
                "timestamp": timestamp
            }

        if not mac in self.nodes:
            self.nodes[mac] = {
                    "topic":f"{config.mqtt.prefix}/{mac}/sensor",
                    "last_ts": timestamp
                    }
        else:
            self.nodes[mac]["last_ts"] = timestamp

        self.client.publish(f"{config.mqtt.prefix}/sensors",
                json.dumps(data))
        self.client.publish(f"{config.mqtt.prefix}/{mac}/sensor",
                json.dumps(data))

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
        status = (event.data["ctl"] & 0x70) >> 4
        msg_id = (event.data["ctl"] & 0x0C) >> 2
        ph_id = event.data["ctl"] & 0x03
        ph_str = str(ph_id) if ph_id else "TOTAL"
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "POWER_METER_STATUS", status,
                timestamp, event.data["rssi"])
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
