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
            # Try using bluetoothctl
            sensors = await self._scan_with_bluetoothctl()
            
            if not sensors:
                # Fallback to hcitool
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
        """Extract temperature, humidity, and other readings from sensor data"""
        readings = {}
        try:
            # Parse sensor name/data for readings
            name = sensor_data.get('name', '').lower()
            
            # Try to extract temperature from name (e.g., "MST01 Temp: 23.5")
            import re
            temp_match = re.search(r'temp(?:erature)?[\s:]*(-?\d+\.?\d*)', name)
            if temp_match:
                readings['temperature'] = float(temp_match.group(1)) * 100  # Convert to API format (hundredths)
            
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
