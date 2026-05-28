"""
BLE Broadcast Listener - Listens for MST01 sensor advertisements
Continuously monitors BLE advertisements and sends sensor data to backend
"""
import asyncio
import logging
from datetime import datetime as dt
import struct
import json

from ttgateway import utils
from ttgateway.http_helper import HttpHelper

logger = logging.getLogger(__name__)


class BLEBroadcastListener:
    """Listens for BLE sensor broadcasts (MST01) and POSTs to backend"""
    
    NE_URL = "http://localhost"
    NE_PORT = 80
    SENSOR_DATA_URL = f"{NE_URL}:{NE_PORT}/api/sensors-data/"
    BUFFER_SIZE = 10  # Buffer sensor readings before posting
    BUFFER_TIMEOUT = 30  # Post every 30 seconds even if buffer not full
    
    def __init__(self):
        self.http = HttpHelper()
        self.task = None
        self.buffer = {}  # {mac_address: sensor_data_dict}
        self.buffer_flush_task = None
        self.is_scanning = False
        
    async def enable(self):
        """Start BLE broadcast listening"""
        try:
            if not self.task:
                logger.info("Enabling BLE broadcast listener")
                self.task = asyncio.create_task(self._listen_loop())
                self.buffer_flush_task = asyncio.create_task(self._buffer_flush_loop())
            return True
        except Exception as e:
            logger.error(f"Failed to enable BLE listener: {e}", exc_info=True)
            return False
    
    async def disable(self):
        """Stop BLE broadcast listening"""
        try:
            if self.task:
                self.task.cancel()
                self.task = None
            if self.buffer_flush_task:
                self.buffer_flush_task.cancel()
                self.buffer_flush_task = None
            logger.info("BLE broadcast listener disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable BLE listener: {e}", exc_info=True)
            return False
    
    async def _listen_loop(self):
        """Main BLE listening loop"""
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            import gi
            gi.require_version('GLib', '2.0')
            from gi.repository import GLib
            
            DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()
            
            # Get bluez adapter
            manager = dbus.Interface(
                bus.get_object('org.bluez', '/'),
                'org.freedesktop.DBus.ObjectManager'
            )
            
            # Listen for new interfaces (advertisement signals)
            manager.connect_to_signal(
                'InterfacesAdded',
                self._on_ble_advertisement
            )
            
            logger.info("BLE listener started - monitoring advertisements")
            
            # Keep listening
            mainloop = GLib.MainLoop()
            while self.is_scanning:
                mainloop.run()
                await asyncio.sleep(0.1)
                
        except ImportError:
            logger.warning("dbus/GLib not available, using fallback HCI socket method")
            await self._listen_loop_hci()
        except Exception as e:
            logger.error(f"BLE listener error: {e}", exc_info=True)
            await asyncio.sleep(5)
    
    async def _listen_loop_hci(self):
        """Fallback: Use direct HCI socket for BLE scanning"""
        try:
            import socket
            import subprocess
            
            # Start hcitool lescan
            proc = await asyncio.create_subprocess_exec(
                'hcitool', 'lescan',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            logger.info("HCI BLE scan started")
            self.is_scanning = True
            
            while self.is_scanning and proc.returncode is None:
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=1
                    )
                    if line:
                        # lescan output format: MAC_ADDRESS TYPE_AND_RSSI_IF_AVAILABLE
                        # We need more detailed info, so also use hcidump
                        pass
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.1)
            
            proc.kill()
            
        except Exception as e:
            logger.error(f"HCI scan error: {e}", exc_info=True)
    
    def _on_ble_advertisement(self, path, interfaces):
        """Handle new BLE advertisement"""
        try:
            # Check if this is a GATT characteristic with advertisement data
            if 'org.bluez.LEAdvertisingManager1' not in interfaces:
                return
            
            props = interfaces['org.bluez.LEAdvertisingManager1']
            
            # Parse manufacturer data for MST01 sensor
            if 'ManufacturerData' in props:
                mfg_data = props['ManufacturerData']
                self._parse_mst01_advertisement(path, mfg_data)
        
        except Exception as e:
            logger.debug(f"Error parsing advertisement: {e}")
    
    def _parse_mst01_advertisement(self, path, mfg_data):
        """Parse MST01 sensor data from BLE advertisement"""
        try:
            # Extract MAC from D-Bus path: /org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX
            if '/dev_' not in path:
                return
            
            mac_part = path.split('/dev_')[1].replace('_', ':').upper()
            
            # Decode manufacturer data (MST01 format)
            # Expected format varies, but typically contains temp/humidity/pressure
            if isinstance(mfg_data, dict):
                for mfg_id, data in mfg_data.items():
                    sensor_data = self._decode_mst01_payload(data, mac_part)
                    if sensor_data:
                        self.buffer[mac_part] = sensor_data
                        logger.debug(f"Buffered sensor {mac_part}: {sensor_data}")
        
        except Exception as e:
            logger.debug(f"Error parsing MST01 advertisement: {e}")
    
    def _decode_mst01_payload(self, data, mac_address):
        """
        Decode MST01 sensor payload from BLE advertisement
        Returns dict with sensor data or None if parsing fails
        """
        try:
            # MST01 payload format (example):
            # May contain temperature, humidity, pressure in different byte positions
            # This is a generic implementation - adjust based on actual MST01 format
            
            if len(data) < 4:
                return None
            
            # Extract values (example - adjust byte positions for real MST01 format)
            # Temperature: bytes 0-1 (in 0.01°C units)
            # Humidity: byte 2
            # Pressure: bytes 3-4
            
            sensor_data = {
                "mac_address": mac_address,
                "datetime": dt.utcnow().strftime("%d/%m/%Y %H:%M"),
                "temperature": 0,
                "humidity": 0,
                "pressure": 0,
                "rssi": -60,  # Will be updated from signal strength
                "battery": 3000,  # Default battery voltage
            }
            
            return sensor_data
        
        except Exception as e:
            logger.debug(f"Error decoding payload: {e}")
            return None
    
    async def _buffer_flush_loop(self):
        """Periodically flush buffered sensor data to backend"""
        while True:
            try:
                await asyncio.sleep(self.BUFFER_TIMEOUT)
                
                if self.buffer:
                    await self._post_buffered_data()
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Buffer flush error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _post_buffered_data(self):
        """POST buffered sensor data to backend"""
        try:
            if not self.buffer:
                return
            
            data_array = list(self.buffer.values())
            body = {"data": data_array}
            
            logger.debug(f"Posting {len(data_array)} sensor readings to backend")
            
            response = await self.http.request(
                "ble_sensors",
                "POST",
                self.SENSOR_DATA_URL,
                body
            )
            
            if response and response.ok:
                logger.info(f"Successfully posted {len(data_array)} sensor readings")
                self.buffer.clear()
            else:
                logger.warning(f"Failed to post sensor data: {response}")
        
        except Exception as e:
            logger.error(f"Error posting buffered data: {e}", exc_info=True)


# Alternative: Simple HCI-based scanner (more reliable)
class BLEHCIScanner:
    """Use HCI socket directly for BLE scanning"""
    
    SENSOR_DATA_URL = "http://localhost:80/api/sensors-data/"
    
    def __init__(self):
        self.http = HttpHelper()
        self.task = None
        self.sensor_cache = {}  # Cache to avoid duplicates: {mac: timestamp}
        self.cache_timeout = 5  # Seconds
    
    async def enable(self):
        """Start BLE scanning"""
        if not self.task:
            self.task = asyncio.create_task(self._scan_loop())
        return True
    
    async def disable(self):
        """Stop BLE scanning"""
        if self.task:
            self.task.cancel()
            self.task = None
        return True
    
    async def _scan_loop(self):
        """Main scan loop using hcidump to capture raw advertisements"""
        try:
            import subprocess
            
            proc = await asyncio.create_subprocess_exec(
                'hcidump',
                '--raw',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            logger.info("HCI scanner started with hcidump")
            
            buffer = b""
            while proc.returncode is None:
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=1
                    )
                    
                    if line:
                        buffer += line
                        # Parse HCI LE Meta Event for advertisements
                        self._parse_hci_event(buffer)
                        buffer = b""
                
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.1)
            
        except FileNotFoundError:
            logger.error("hcidump not found. Install: apt-get install bluez")
        except Exception as e:
            logger.error(f"HCI scanner error: {e}", exc_info=True)
            await asyncio.sleep(5)
    
    def _parse_hci_event(self, data):
        """Parse HCI event for advertisement data"""
        try:
            # HCI format parsing - extract advertisement data
            # This is complex - actual implementation would need proper HCI parsing
            pass
        except Exception as e:
            logger.debug(f"Error parsing HCI event: {e}")
