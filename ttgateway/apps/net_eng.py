from datetime import datetime as dt

from ttgwlib import EventType
import logging

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
            (EventType.UNPROV_DISC, self.unprov_handler),
            (EventType.PROV_COMPLETE, self.prov_complete_handler),
            (EventType.PROV_LINK_CLOSED, self.prov_link_closed_handler),
        ]
        self.new_node_devkey = None # ProvComplete only gives DevKey, which is
                                    # used to get the new node
        self.logger = logging.getLogger(__name__)

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

    def _parse_mst01_payload(self, payload):
        """Parse Minew MST01 sensor manufacturer data (Company ID 0x0639).
        
        Supports:
        - T&H live frame: payload[0]=0xCA, payload[1]=0x05
          Temperature and humidity readings from bytes 5-8
        - Heartbeat/info frame: payload[0]=0xCA, payload[1]=0x00
          Battery percentage and voltage from bytes 3 and 8
        
        Args:
            payload: Bytes object containing manufacturer-specific data
            
        Returns:
            dict with parsed fields (frame, temperature, humidity, etc.) or None
        """
        if not isinstance(payload, (bytes, bytearray)):
            return None
        
        if len(payload) < 9 or payload[0] != 0xCA:
            return None

        try:
            # T&H live frame
            if payload[1] == 0x05:
                temp_c = payload[5] + payload[6] / 256.0
                hum_pct = payload[7] + payload[8] / 256.0
                return {
                    "frame": "TH",
                    "temperature": round(temp_c, 2),
                    "humidity": round(hum_pct, 1),
                }
            
            # Heartbeat/info frame
            if payload[1] == 0x00:
                return {
                    "frame": "INFO",
                    "battery_pct": payload[8],
                    "battery_mv": payload[3] * 100,
                }
        except (IndexError, TypeError):
            pass
        
        return None

    def _parse_beaconx_pro_payload(self, payload):
        """Parse BeaconX Pro sensor data from service data."""
        if not isinstance(payload, (bytes, bytearray)) or len(payload) < 8:
            return None
        # Heuristic scan for plausible temp/humidity pairs inside BeaconX service data.
        for offset in range(0, len(payload) - 4):
            try:
                temperature = int.from_bytes(payload[offset:offset + 2], "big") / 100.0
                humidity = int.from_bytes(payload[offset + 2:offset + 4], "big") / 100.0
                if 0 <= temperature <= 80 and 0 <= humidity <= 100:
                    return {
                        "frame": "BEACONX",
                        "temperature": temperature,
                        "humidity": humidity,
                    }
            except Exception:
                continue
        return None

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

    async def unprov_handler(self, event):
        """Handle unprovisioned BLE adverts and forward basic info to NE.

        Creates a sensor entry (`sensors-new`) and posts a minimal
        telemetry sample (`sensors-data`) containing RSSI and timestamp.
        This enables MST01/BeaconX and other non-mesh beacons to appear
        in the NE UI even when they cannot be provisioned.
        
        Supports structured parsing of:
        - Minew MST01 (Company ID 0x0639): T&H live frame and heartbeat frames
        - BeaconX Pro: Service data with T&H sensor readings
        """
        # Log raw event data for diagnostics and vendor parsing
        try:
            self.logger.debug("Unprovisioned advert event data: %s", event.data)
        except Exception:
            pass

        adv_addr = event.data.get("adv_addr")
        if not adv_addr:
            return
        mac = adv_addr.hex().upper()

        # Try to create a sensor entry (ignore failures)
        body_new = {"mac_address": mac}
        try:
            await self.http.request("ne_sensor", "POST", self.SENSOR_NEW_URL, body_new)
        except Exception:
            # don't fail the handler on HTTP errors
            pass

        # Initialize fields
        temperature = None
        humidity = None
        battery = None

        # Try structured parsing of manufacturer data
        manufacturer_data = event.data.get("manufacturer_data", {})
        if isinstance(manufacturer_data, dict):
            # Check for Minew MST01 (Company ID 0x0639 = 1593)
            if 0x0639 in manufacturer_data:
                payload = manufacturer_data[0x0639]
                if isinstance(payload, (bytes, bytearray)):
                    parsed = self._parse_mst01_payload(payload)
                    if parsed:
                        temperature = parsed.get("temperature")
                        humidity = parsed.get("humidity")
                        frame_type = parsed.get("frame", "UNKNOWN")
                        self.logger.info(
                            "Parsed MST01 (%s) advertisement: mac=%s temp=%s humidity=%s",
                            frame_type, mac, temperature, humidity
                        )
                        if frame_type == "INFO":
                            battery = parsed.get("battery_pct")

        # Fallback: Try to parse other advertisement formats if structured parsing didn't work
        if temperature is None and humidity is None:
            # Try to find any raw bytes that might contain data
            for k in ("adv_data", "adv_payload", "data"):
                if k in event.data and event.data[k]:
                    manuf_bytes = event.data[k]
                    if isinstance(manuf_bytes, (bytes, bytearray)):
                        try:
                            ascii = ''.join((chr(b) if 32 <= b <= 126 else '.') for b in manuf_bytes)
                            if 'BEACONX' in ascii.upper():
                                parsed = self._parse_beaconx_pro_payload(manuf_bytes)
                                if parsed:
                                    temperature = parsed.get("temperature")
                                    humidity = parsed.get("humidity")
                                    self.logger.info(
                                        "Parsed BeaconX Pro advertisement: mac=%s temp=%s humidity=%s",
                                        mac, temperature, humidity
                                    )
                                    break
                        except Exception:
                            pass

        # Post a telemetry datapoint with parsed fields
        rssi = event.data.get("rssi", 0)
        sample = {
            "mac_address": mac,
            "datetime": dt.utcnow().strftime("%d/%m/%Y %H:%M"),
            "temperature": temperature,
            "humidity": humidity,
            "pressure": None,
            "rssi": rssi,
            "battery": battery,
        }
        body_data = {"data": [sample]}
        try:
            await self.http.request("ne_data", "POST", self.SENSOR_DATA_URL, body_data)
        except Exception:
            pass