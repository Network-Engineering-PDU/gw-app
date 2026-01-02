import os
import time
import asyncio

from ttgwlib import EventType

from ttgateway.config import config

class CsvApp:
    HEADERS = ["MAC", "UNICAST_ADDRESS", "TYPE", "VALUE", "TIMESTAMP", "RSSI"]
    def __init__(self):
        self.file = os.path.join(config.TT_DIR, "telemetry.csv")
        self.handlers = []
        if self.telemetry:
            self.handlers.append((EventType.TEMP_DATA, self.telemetry_handler))
            self.handlers.append((EventType.TEMP_DATA_RELIABLE,
                self.telemetry_handler))
        if self.co2:
            self.handlers.append((EventType.IAQ_DATA, self.iaq_handler))
            self.handlers.append((EventType.CO2_DATA, self.co2_handler))
        if self.battery:
            self.handlers.append((EventType.BAT_DATA, self.battery_handler))
        if self.power_meter:
            self.handlers.append((EventType.PWMT_DATA, self.pwmt_data_handler))

    @property
    def telemetry(self):
        return config.csv.telemetry

    @property
    def battery(self):
        return config.csv.battery

    @property
    def co2(self):
        return config.csv.co2

    @property
    def power_meter(self):
        return config.csv.power_meter

    @property
    def macs(self):
        return config.csv.macs

    def use_node(self, node):
        if not self.macs:
            return True
        return node.mac.hex() in self.macs

    async def enable(self):
        if not os.path.exists(self.file):
            await asyncio.to_thread(self.write, *self.HEADERS)
        return True

    async def disable(self):
        return True

    def write(self, mac, unicast_addr, _type, value, timestamp, rssi):
        with open(self.file, "a") as f:
            f.write(",".join((mac, str(unicast_addr), _type, str(value),
                str(timestamp), str(rssi))) + "\n")

    async def telemetry_handler(self, event):
        if not self.use_node(event.node):
            return
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
        if not self.use_node(event.node):
            return
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "BAT", event.data["bat"],
                int(time.time()), event.data["rssi"])

    async def iaq_handler(self, event):
        if not self.use_node(event.node):
            return
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
        if not self.use_node(event.node):
            return
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "CO2", event.data["co2"],
                int(time.time()), event.data["rssi"])

    async def pwmt_data_handler(self, event):
        if not self.use_node(event.node):
            return
        timestamp = int(time.time())
        status = (event.data["ctl"] & 0x70) >> 4
        message_id = (event.data["ctl"] & 0x0C) >> 2
        phase_id = event.data["ctl"] & 0x03
        phase_str = str(phase_id) if phase_id else "TOTAL"
        await asyncio.to_thread(self.write, event.node.mac.hex(),
                event.node.unicast_addr, "POWER_METER_STATUS", status,
                timestamp, event.data["rssi"])
        if phase_id == 0:
            if message_id == 0:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ACTIVE_POWER_{phase_str}",
                        event.data["p_tot"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"REACTIVE_POWER_{phase_str}",
                        event.data["q_tot"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"APPARENT_POWER_{phase_str}",
                        event.data["s_tot"], timestamp, event.data["rssi"])
            elif message_id == 1:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"PHASE12_{phase_str}",
                        event.data["ph12"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"PHASE23_{phase_str}",
                        event.data["ph23"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"PHASE31_{phase_str}",
                        event.data["ph31"], timestamp, event.data["rssi"])
            elif message_id == 2:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"VOLTAGE12_{phase_str}",
                        event.data["v12"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"VOLTAGE23_{phase_str}",
                        event.data["v23"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"VOLTAGE31_{phase_str}",
                        event.data["v31"], timestamp, event.data["rssi"])
            elif message_id == 3:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ENERGY_{phase_str}",
                        event.data["e_tot"], timestamp, event.data["rssi"])
        else:
            if message_id == 0:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"VOLTAGE_{phase_str}",
                        event.data["v"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"CURRENT_{phase_str}",
                        event.data["i"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"FREQUENCY_{phase_str}",
                        event.data["f"], timestamp, event.data["rssi"])
            elif message_id == 1:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ACTIVE_POWER_{phase_str}",
                        event.data["p"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"POWER_FACTOR_{phase_str}",
                        event.data["pf"], timestamp, event.data["rssi"])
            elif message_id == 2:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"REACTIVE_POWER_{phase_str}",
                        event.data["q"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"APPARENT_POWER_{phase_str}",
                        event.data["s"], timestamp, event.data["rssi"])
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"PHASE_{phase_str}",
                        event.data["ph"], timestamp, event.data["rssi"])
            elif message_id == 3:
                await asyncio.to_thread(self.write, event.node.mac.hex(),
                        event.node.unicast_addr, f"ENERGY_{phase_str}",
                        event.data["e"], timestamp, event.data["rssi"])
