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

    def _parse_mst01_payload(self, payload):
        """Parse Minew MST01 sensor manufacturer data (Company ID 0x0639).
        
        Supports:
        - T&H live frame: mfr_data[0]=0xCA, mfr_data[1]=0x05
        - Heartbeat/info frame: mfr_data[0]=0xCA, mfr_data[1]=0x00
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
        if not isinstance(payload, (bytes, bytearray)) or len(payload) < 8:
            return None
        # Heuristic scan for plausible temp/humidity pairs inside BeaconX service data.
        for offset in range(0, len(payload) - 4):
            try:
                temperature = int.from_bytes(payload[offset:offset + 2], "big") / 100.0
                humidity = int.from_bytes(payload[offset + 2:offset + 4], "big") / 100.0
                if 0 <= temperature <= 80 and 0 <= humidity <= 100:
                    return {
                        "temperature": temperature,
                        "humidity": humidity,
                    }
            except Exception:
                continue
        return None

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

    async def unprov_handler(self, event):
        """Handle unprovisioned BLE adverts and forward basic info to NE.

        Creates a sensor entry (`sensors-new`) and posts a minimal
        telemetry sample (`sensors-data`) containing RSSI and timestamp.
        This enables MST01/BeaconX and other non-mesh beacons to appear
        in the NE UI even when they cannot be provisioned.
        """
        adv_addr = event.data.get("adv_addr")
        if not adv_addr:
            return
        mac = adv_addr.hex().upper()

        # Log event details for screen/debug output, including UUID and RSSI.
        try:
            self.logger.info(
                "Unprovisioned advert received: mac=%s uuid=%s rssi=%s "
                "gatt_supported=%s adv_addr_type=%s",
                mac,
                event.data.get("uuid").hex() if event.data.get("uuid") else None,
                event.data.get("rssi"),
                event.data.get("gatt_supported"),
                event.data.get("adv_addr_type"),
            )
            self.logger.debug("Unprovisioned advert raw event data: %s", event.data)
        except Exception:
            pass

        # Try to create a sensor entry (ignore failures)
        body_new = {"mac_address": mac}
        try:
            await self.http.request("ne_sensor", "POST", self.SENSOR_NEW_URL, body_new)
        except Exception:
            # don't fail the handler on HTTP errors
            pass

        # Try to extract vendor-specific fields from advertisement payloads or bluetoothctl info
        temperature = None
        humidity = None
        battery = None
        manuf_bytes = None
        local_name = event.data.get("local_name")
        manufacturer_data = event.data.get("manufacturer_data")
        service_data = event.data.get("service_data")

        if local_name:
            self.logger.info("Unprovisioned advert local_name=%s", local_name)

        if isinstance(manufacturer_data, dict):
            for key, payload in manufacturer_data.items():
                if isinstance(payload, (bytes, bytearray)) and payload:
                    self.logger.debug("ManufacturerData 0x%04x=%s", key, payload.hex())
                    if key == 0x0639:
                        parsed = self._parse_mst01_payload(payload)
                        if parsed:
                            temperature = parsed.get("temperature")
                            humidity = parsed.get("humidity")
                            self.logger.info("Parsed MST01 advertisement: temp=%s humidity=%s", temperature, humidity)
                    if not manuf_bytes:
                        manuf_bytes = payload
                    break
        elif isinstance(manufacturer_data, (bytes, bytearray)):
            manuf_bytes = manufacturer_data

        if not manuf_bytes and isinstance(service_data, dict):
            for key, payload in service_data.items():
                if isinstance(payload, (bytes, bytearray)) and payload:
                    self.logger.debug("ServiceData %s=%s", key, payload.hex())
                    if key == "feab" or key == "FEAB":
                        parsed = self._parse_beaconx_pro_payload(payload)
                        if parsed:
                            temperature = parsed.get("temperature")
                            humidity = parsed.get("humidity")
                            self.logger.info("Parsed BeaconX Pro advertisement: temp=%s humidity=%s", temperature, humidity)
                    if not manuf_bytes:
                        manuf_bytes = payload
                    break
        elif not manuf_bytes and isinstance(service_data, (bytes, bytearray)):
            manuf_bytes = service_data

        if isinstance(manuf_bytes, (bytes, bytearray)):
            try:
                # convert to printable ascii for heuristic parsing
                ascii = ''.join((chr(b) if 32 <= b <= 126 else '.') for b in manuf_bytes)
                self.logger.debug("Unprovisioned advert payload ascii=%s", ascii)
                # only apply loose heuristics when exact payload parsing did not already succeed
                if temperature is None and humidity is None and (
                    'MST' in ascii or 'BEACON' in ascii.upper() or 'BEACONX' in ascii.upper()
                ):
                    import re
                    nums = re.findall(r"\d{3,5}", ascii)
                    if nums:
                        # heuristic: if two numbers, treat as temp then battery
                        if len(nums) >= 2:
                            try:
                                temperature = int(nums[0])
                            except:
                                temperature = None
                            try:
                                battery = int(nums[1])
                            except:
                                battery = None
                        else:
                            val = int(nums[0])
                            # if value looks like mV battery
                            if 2000 <= val <= 4200:
                                battery = val
                            else:
                                temperature = val
            except Exception:
                pass

        if not manuf_bytes and local_name and 'BEACONX' in local_name.upper():
            self.logger.debug("BeaconX Pro advert detected by local_name=%s", local_name)
        
        if isinstance(manufacturer_data, dict) and 0x0639 in manufacturer_data:
            self.logger.debug("Minew MST01 candidate manufacturer payload=%s", manufacturer_data[0x0639].hex())
            if manufacturer_data[0x0639] and not temperature:
                manuf_bytes = manufacturer_data[0x0639]
                try:
                    ascii = ''.join((chr(b) if 32 <= b <= 126 else '.') for b in manuf_bytes)
                    self.logger.debug("Minew payload ascii=%s", ascii)
                except Exception:
                    pass

        # Post a minimal telemetry datapoint (RSSI and any parsed fields)
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
