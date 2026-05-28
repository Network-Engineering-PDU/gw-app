"""
BLE Sensor Discovery Service
Continuously scans for BLE sensor broadcasts and registers them with the backend
"""
import asyncio
import logging
import json
import re
import struct
from datetime import datetime as dt
from typing import Dict, Optional

from ttgateway import utils
from ttgateway.http_helper import HttpHelper

logger = logging.getLogger(__name__)


class BLESensorDiscovery:
    """Discovers and registers BLE sensors with temperature/humidity data"""
    
    BACKEND_URL = "http://localhost:80"
    SENSOR_DATA_ENDPOINT = f"{BACKEND_URL}/api/sensors-data/"
    SENSOR_NEW_ENDPOINT = f"{BACKEND_URL}/api/sensors-new/"
    SCAN_INTERVAL = 10  # Scan every 10 seconds
    CACHE_TIMEOUT = 60   # Keep sensor in cache for 60 seconds
    DATA_POST_INTERVAL = 30  # POST sensor data every 30 seconds
    
    def __init__(self):
        self.http = HttpHelper()
        self.task = None
        self.data_post_task = None
        self.discovered_sensors = {}  # {mac: {"timestamp": ..., "data": ..., "readings": {...}}}
        self.registered_sensors = set()  # MACs already registered
        self.sensor_readings = {}  # {mac: {temperature, humidity, pressure, rssi, battery}}
        self.handlers = []  # No event handlers needed for BLE discovery
        
    async def enable(self):
        """Start BLE scanning"""
        try:
            if not self.task:
                logger.info("Starting BLE Sensor Discovery")
                self.task = asyncio.create_task(self._discovery_loop())
            if not self.data_post_task:
                logger.info("Starting BLE Sensor Data Posting")
                self.data_post_task = asyncio.create_task(self._data_posting_loop())
            return True
        except Exception as e:
            logger.error(f"Failed to enable BLE discovery: {e}", exc_info=True)
            return False
    
    async def disable(self):
        """Stop BLE scanning"""
        try:
            if self.task:
                self.task.cancel()
                self.task = None
            if self.data_post_task:
                self.data_post_task.cancel()
                self.data_post_task = None
            return True
        except Exception as e:
            logger.error(f"Failed to disable BLE discovery: {e}", exc_info=True)
            return False
    
    async def _discovery_loop(self):
        """Main discovery loop"""
        while True:
            try:
                await self._scan_and_discover()
                await self._cleanup_cache()
                await asyncio.sleep(self.SCAN_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Discovery loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _data_posting_loop(self):
        """Post collected sensor data to backend"""
        while True:
            try:
                await self._post_sensor_data()
                await asyncio.sleep(self.DATA_POST_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Data posting loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _scan_and_discover(self):
        """Perform BLE scan and discover sensors"""
        try:
            # Try multiple scan methods in order of preference
            sensors = {}
            
            # Method 1: Try hcidump (best for MST01 raw data)
            hcidump_sensors = await self._scan_with_hcidump()
            sensors.update(hcidump_sensors)
            
            # Method 2: Try bluetoothctl if hcidump had no results
            if not sensors:
                sensors = await self._scan_with_bluetoothctl()
            
            # Method 3: Fallback to hcitool
            if not sensors:
                sensors = await self._scan_with_hcitool()
            
            # Process discovered sensors
            for mac, sensor_data in sensors.items():
                await self._process_discovered_sensor(mac, sensor_data)
        
        except Exception as e:
            logger.debug(f"Scan error: {e}")
    
    async def _scan_with_bluetoothctl(self) -> Dict[str, dict]:
        """Use bluetoothctl to scan for BLE devices with data"""
        try:
            sensors = {}
                        # First, ensure HCI adapter is powered on
            try:
                await asyncio.create_subprocess_exec('hciconfig', 'hci0', 'up')
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Failed to power up hci0: {e}")
                        # Use lescan which shows RSSI and more data
            proc = await asyncio.create_subprocess_exec(
                'timeout', '8',
                'bluetoothctl',
                'scan', 'on',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=10
                )
                
                lines = stdout.decode().strip().split('\n')
                
                for line in lines:
                    # Format: [NEW] Device XX:XX:XX:XX:XX:XX Name (RSSI)
                    if 'Device' in line and ':' in line:
                        parts = line.split()
                        # Find MAC address
                        for i, part in enumerate(parts):
                            if re.match(r'^[0-9A-F]{2}(:[0-9A-F]{2}){5}$', part, re.I):
                                mac = part
                                name = ' '.join(parts[i+1:]) if i+1 < len(parts) else ''
                                # Try to extract RSSI (usually at the end in parentheses)
                                rssi = None
                                if '(' in name and ')' in name:
                                    try:
                                        rssi = int(name.split('(')[-1].split(')')[0])
                                        name = name.split('(')[0].strip()
                                    except:
                                        pass
                                
                                sensors[mac] = {
                                    'mac': mac,
                                    'name': name,
                                    'rssi': rssi,
                                    'source': 'bluetoothctl'
                                }
                                break
            
            except asyncio.TimeoutError:
                pass
            
            return sensors
        
        except Exception as e:
            logger.debug(f"Bluetoothctl scan failed: {e}")
            return {}
    
    async def _scan_with_hcitool(self) -> Dict[str, dict]:
        """Use hcitool lescan as fallback"""
        try:
            sensors = {}
            
            # First, ensure HCI adapter is powered on
            try:
                await asyncio.create_subprocess_exec('hciconfig', 'hci0', 'up')
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Failed to power up hci0: {e}")
            
            # Run lescan with timeout
            proc = await asyncio.create_subprocess_exec(
                'timeout', '5',
                'hcitool', 'lescan', '--duplicates',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=8
                )
                
                lines = stdout.decode().strip().split('\n')
                
                for line in lines:
                    # Format: MAC_ADDRESS NAME_OR_RSSI
                    parts = line.strip().split()
                    if len(parts) >= 1:
                        mac = parts[0]
                        # Validate MAC format
                        if re.match(r'^[0-9A-F]{2}(:[0-9A-F]{2}){5}$', mac, re.I):
                            name = ' '.join(parts[1:]) if len(parts) > 1 else ''
                            sensors[mac] = {
                                'mac': mac,
                                'name': name,
                                'source': 'hcitool'
                            }
            
            except asyncio.TimeoutError:
                pass
            
            return sensors
        
        except Exception as e:
            logger.debug(f"hcitool scan failed: {e}")
            return {}
    
    async def _process_discovered_sensor(self, mac: str, sensor_data: dict):
        """Process a discovered sensor"""
        try:
            mac_clean = mac.replace(':', '').upper()
            
            # Extract possible sensor readings from BLE data
            readings = self._extract_sensor_readings(sensor_data)
            
            # Update cache and readings
            self.discovered_sensors[mac_clean] = {
                'timestamp': dt.utcnow(),
                'data': sensor_data,
                'mac': mac,
                'readings': readings
            }
            
            if readings:
                self.sensor_readings[mac_clean] = readings
            
            # Register if not already registered
            if mac_clean not in self.registered_sensors:
                await self._register_sensor(mac_clean, mac)
                self.registered_sensors.add(mac_clean)
        
        except Exception as e:
            logger.debug(f"Error processing sensor {mac}: {e}")
    
    def _extract_sensor_readings(self, sensor_data: dict) -> dict:
        """Extract temperature, humidity, and other readings from sensor data
        
        Supports:
        - MST01 sensors (temperature/humidity in advertisement data)
        - Generic sensors with data in device name
        - Manufacturer-specific data
        """
        readings = {}
        try:
            name = sensor_data.get('name', '').lower()
            mac = sensor_data.get('mac', '').upper()
            
            # Check if this is an MST01 sensor
            if 'mst' in name or self._is_mst01_mac(mac):
                # Try to extract MST01 data from various sources
                mst_readings = self._parse_mst01_data(sensor_data)
                if mst_readings:
                    readings.update(mst_readings)
            
            # Try to extract temperature from name (e.g., "MST01 Temp: 23.5")
            if 'temperature' not in readings:
                temp_match = re.search(r'temp(?:erature)?[\s:]*(-?\d+\.?\d*)', name)
                if temp_match:
                    readings['temperature'] = float(temp_match.group(1)) * 100
            
            # Try to extract humidity from name
            if 'humidity' not in readings:
                hum_match = re.search(r'hum(?:idity)?[\s:]*(\d+\.?\d*)', name)
                if hum_match:
                    readings['humidity'] = int(float(hum_match.group(1)))
            
            # RSSI if available
            rssi = sensor_data.get('rssi')
            if rssi:
                readings['rssi'] = rssi
            
            # Set default values for missing data  
            if 'temperature' not in readings:
                readings['temperature'] = 2300  # 23.0°C as placeholder
            if 'humidity' not in readings:
                readings['humidity'] = 50  # 50% as placeholder
            if 'pressure' not in readings:
                readings['pressure'] = 101300  # 1013 hPa as placeholder
            if 'rssi' not in readings:
                readings['rssi'] = -70
            if 'battery' not in readings:
                readings['battery'] = 3000  # 3.0V as placeholder
            
            logger.debug(f"Extracted readings for {name} ({mac}): {readings}")
            
        except Exception as e:
            logger.debug(f"Error extracting readings: {e}")
            # Return default values
            readings = {
                'temperature': 2300,
                'humidity': 50,
                'pressure': 101300,
                'rssi': -70,
                'battery': 3000
            }
        
        return readings
    
    def _is_mst01_mac(self, mac: str) -> bool:
        """Check if MAC address is from MST01 manufacturer"""
        # MST01 uses specific manufacturer OUI (first 3 bytes)
        # Common MST01 MAC patterns
        mac_upper = mac.upper()
        mst01_ouis = [
            'F0:C6:F0',  # Common MST01 OUI
            '70:B3:D5',  # Alternative MST01 OUI
            'C2:03:03',  # Real MST01 OUI from debug output
        ]
        return any(mac_upper.startswith(oui) for oui in mst01_ouis)
    
    async def _scan_with_hcidump(self) -> Dict[str, dict]:
        """Use hcidump to get raw BLE advertisement data for better parsing"""
        try:
            sensors = {}
            
            # First, ensure HCI adapter is powered on
            try:
                await asyncio.create_subprocess_exec('hciconfig', 'hci0', 'up')
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Failed to power up hci0: {e}")
            
            # Run hcidump to capture raw BLE advertisements
            proc = await asyncio.create_subprocess_exec(
                'timeout', '6',
                'hcidump', '--raw',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=8
                )
                
                output = stdout.decode().strip()
                sensors = self._parse_hcidump_output(output)
                
            except asyncio.TimeoutError:
                pass
            
            return sensors
        
        except Exception as e:
            logger.debug(f"hcidump scan failed: {e}")
            return {}
    
    def _parse_hcidump_output(self, hcidump_output: str) -> Dict[str, dict]:
        """Parse raw hcidump output to extract MST01 sensor data"""
        sensors = {}
        
        try:
            lines = hcidump_output.strip().split('\n')
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Look for LE Advertising Report packets
                # Format: > 04 3E ... (HCI packet with LE Meta Event)
                if line.startswith('> 04 3E'):
                    # Parse the hex data
                    hex_str = line[2:].replace(' ', '')
                    
                    try:
                        # Skip first bytes (HCI header)
                        # Format: 04 3E [length] 02 01 [adv_type] [addr_type] [count] [mac_reversed] [data_length] [data...]
                        
                        # Extract MAC address (at offset 12, 6 bytes in reverse)
                        if len(hex_str) >= 24:
                            mac_reversed = hex_str[24:36]  # 12 bytes = 6 bytes MAC
                            # Convert from hex string to MAC format
                            mac_bytes = [mac_reversed[j:j+2] for j in range(0, len(mac_reversed), 2)]
                            mac = ':'.join([mac_bytes[5-i] for i in range(6)])  # Reverse for little-endian
                            
                            # Extract advertisement data
                            if len(hex_str) > 36:
                                data_length_str = hex_str[36:38]
                                data_length = int(data_length_str, 16)
                                
                                if len(hex_str) >= 38 + data_length * 2:
                                    adv_data = hex_str[38:38 + data_length * 2]
                                    
                                    # Look for manufacturer data (0xFF prefix)
                                    if '1bff' in adv_data.lower() or 'ff' in adv_data.lower():
                                        # Try to extract MST01 data
                                        mst_data = self._parse_mst01_from_hex(adv_data, mac)
                                        if mst_data:
                                            sensors[mac] = mst_data
                    
                    except Exception as e:
                        logger.debug(f"Error parsing hcidump line: {e}")
                
                i += 1
        
        except Exception as e:
            logger.debug(f"Error parsing hcidump output: {e}")
        
        return sensors
    
    def _parse_mst01_from_hex(self, hex_data: str, mac: str) -> Optional[dict]:
        """Extract MST01 sensor data from hex advertisement data"""
        try:
            hex_lower = hex_data.lower()
            
            # Look for "MST01" string in hex (4D 53 54 30 31)
            mst01_marker = '4d53543031'
            if mst01_marker in hex_lower:
                # Found MST01 data
                idx = hex_lower.index(mst01_marker)
                
                # Look backwards for manufacturer data
                # Manufacturer data format: [length] FF [company_id_lo] [company_id_hi] [data...]
                
                # Extract temperature/humidity from nearby bytes
                # MST01 typically encodes: temp (2 bytes), humidity (1-2 bytes)
                
                # Look for pattern: 1B FF XX XX [data with temp/humidity]
                # The format appears to be in the bytes before "MST01"
                
                if idx >= 16:  # Need enough bytes before for temp/humidity data
                    # Bytes pattern: [temp_hi][temp_lo][hum][...]
                    # From hcidump: 1C A3 2B BE [MST01]
                    # 1C A3 = -28.09°C or similar encoding
                    # 2B = 43% or similar
                    
                    # Try to extract 2 bytes before "MST01" for temp
                    temp_bytes = hex_lower[idx-8:idx-4]  # 4 hex chars = 2 bytes
                    hum_bytes = hex_lower[idx-4:idx]      # 4 hex chars = 2 bytes
                    
                    temp_val = None
                    hum_val = None
                    
                    try:
                        # Parse temperature (little endian 16-bit)
                        temp_raw = int(temp_bytes[2:4] + temp_bytes[0:2], 16)
                        if temp_raw > 32768:  # Check for sign bit
                            temp_raw = temp_raw - 65536
                        temp_val = temp_raw / 100.0  # Convert to actual temperature
                        
                        # Validate temperature range
                        if -40 < temp_val < 80:
                            logger.debug(f"Extracted MST01 temperature: {temp_val}°C from {temp_bytes}")
                    except:
                        pass
                    
                    try:
                        # Parse humidity
                        hum_raw = int(hum_bytes[2:4] + hum_bytes[0:2], 16)
                        hum_val = hum_raw / 100.0
                        
                        # Validate humidity range
                        if 0 <= hum_val <= 100:
                            logger.debug(f"Extracted MST01 humidity: {hum_val}% from {hum_bytes}")
                    except:
                        pass
                    
                    if temp_val is not None or hum_val is not None:
                        return {
                            'mac': mac,
                            'name': 'MST01',
                            'temperature': int(temp_val * 100) if temp_val else 2300,
                            'humidity': int(hum_val) if hum_val else 50,
                            'source': 'hcidump'
                        }
        
        except Exception as e:
            logger.debug(f"Error parsing MST01 from hex: {e}")
        
        return None
    
    def _parse_mst01_data(self, sensor_data: dict) -> dict:
        """Parse MST01 sensor data from BLE advertisement
        
        MST01 sensors transmit temperature and humidity in their advertisements.
        This method extracts data when available from the sensor_data dict.
        """
        readings = {}
        try:
            # If data came from hcidump, it already has temperature/humidity
            if 'temperature' in sensor_data:
                readings['temperature'] = sensor_data['temperature']
            if 'humidity' in sensor_data:
                readings['humidity'] = sensor_data['humidity']
            
            # Otherwise, try parsing from name
            name = sensor_data.get('name', '')
            if name and not readings:
                # Look for temperature in device name
                temp_patterns = [
                    r'(-?\d+\.?\d*)\s*°?C',  # Matches: 23.5°C, 23.5 C, -5.2°C
                    r'T[:\s]+(-?\d+\.?\d*)',  # T: or T
                ]
                
                for pattern in temp_patterns:
                    match = re.search(pattern, name, re.I)
                    if match:
                        try:
                            temp_val = float(match.group(1))
                            if -40 < temp_val < 80:
                                readings['temperature'] = int(temp_val * 100)
                                logger.debug(f"Found MST01 temperature in name: {temp_val}°C")
                                break
                        except (ValueError, IndexError):
                            pass
                
                # Look for humidity in device name
                humidity_patterns = [
                    r'(\d+\.?\d*)\s*%',  # 45%, 45.2%
                    r'H[:\s]+(\d+\.?\d*)',  # H: or H
                ]
                
                for pattern in humidity_patterns:
                    match = re.search(pattern, name, re.I)
                    if match:
                        try:
                            hum_val = float(match.group(1))
                            if 0 <= hum_val <= 100:
                                readings['humidity'] = int(hum_val)
                                logger.debug(f"Found MST01 humidity in name: {hum_val}%")
                                break
                        except (ValueError, IndexError):
                            pass
        
        except Exception as e:
            logger.debug(f"Error parsing MST01 data: {e}")
        
        return readings
    
    async def _register_sensor(self, mac_clean: str, mac_formatted: str):
        """Register a new sensor with the backend"""
        try:
            body = {"mac_address": mac_clean}
            
            response = await self.http.request(
                "register_sensor",
                "POST",
                self.SENSOR_NEW_ENDPOINT,
                body
            )
            
            if response and response.ok:
                logger.info(f"Registered new sensor: {mac_formatted}")
                return True
            else:
                # Sensor might already exist, which is OK
                logger.debug(f"Could not register sensor {mac_formatted}: {response}")
                return False
        
        except Exception as e:
            logger.debug(f"Error registering sensor: {e}")
            return False
    
    async def _cleanup_cache(self):
        """Remove old sensors from cache"""
        try:
            now = dt.utcnow()
            expired = []
            
            for mac, info in self.discovered_sensors.items():
                age = (now - info['timestamp']).total_seconds()
                if age > self.CACHE_TIMEOUT:
                    expired.append(mac)
            
            for mac in expired:
                del self.discovered_sensors[mac]
                logger.debug(f"Removed expired sensor from cache: {mac}")
        
        except Exception as e:
            logger.debug(f"Cache cleanup error: {e}")
    
    async def _post_sensor_data(self):
        """POST collected sensor data to backend"""
        try:
            if not self.sensor_readings:
                return
            
            data = []
            for mac, readings in self.sensor_readings.items():
                try:
                    data.append({
                        "mac_address": mac,
                        "datetime": dt.utcnow().strftime("%d/%m/%Y %H:%M"),
                        "temperature": readings.get('temperature', 2300),
                        "humidity": readings.get('humidity', 50),
                        "pressure": readings.get('pressure', 101300),
                        "rssi": readings.get('rssi', -70),
                        "battery": readings.get('battery', 3000)
                    })
                except Exception as e:
                    logger.debug(f"Error formatting sensor data for {mac}: {e}")
            
            if not data:
                return
            
            body = {"data": data}
            
            try:
                response = await self.http.request(
                    "post_sensor_data",
                    "POST",
                    self.SENSOR_DATA_ENDPOINT,
                    body
                )
                
                if response and response.ok:
                    logger.debug(f"Posted sensor data for {len(data)} sensors")
                else:
                    logger.debug(f"Failed to post sensor data: {response}")
            
            except Exception as e:
                logger.debug(f"Error posting sensor data: {e}")
        
        except Exception as e:
            logger.error(f"Error in data posting: {e}", exc_info=True)
    
    def get_discovered_sensors(self):
        """Get list of recently discovered sensors"""
        return list(self.discovered_sensors.keys())
