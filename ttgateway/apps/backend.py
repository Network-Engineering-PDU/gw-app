import asyncio
import logging
from datetime import datetime as dt
from datetime import timedelta

from ttgwlib import Node
from ttgwlib import EventType as LibEventType

from ttgateway.config import config
from ttgateway.utils import periodic_task
from ttgateway.http_helper import HttpHelper
from ttgateway.backup_manager import BackupManager
from ttgateway import utils

logger = logging.getLogger(__name__)

class BackendApp:
    DOWNLOAD_NODE_TIMEOUT = timedelta(seconds=600)
    def __init__(self, server):
        self.handlers = [
                (LibEventType.UNKNOWN_NODE, self.unknown_node_handler),
        ]
        self.server = server
        self.http = HttpHelper(self.url, self.user, self.password)
        self.backup = BackupManager("backend", server.event_handler)
        self.datacenter_id = ""
        self.tel_task = None
        self.bat_task = None
        self.pwmt_task = None
        self.bak_task = None
        self.tel_last_sent = dt.fromtimestamp(0)
        self.bat_last_sent = dt.fromtimestamp(0)
        self.pwmt_last_sent = dt.fromtimestamp(0)
        self.last_download_attempt = {}

    @property
    def url(self):
        return config.backend.url

    @property
    def company(self):
        return config.backend.company

    @property
    def slug(self):
        return "" # f"/{self.company}" if multi-database; "" if single-database

    @property
    def device_id(self):
        return config.backend.device_id

    @property
    def user(self):
        return config.backend.user

    @property
    def password(self):
        return config.backend.password

    @property
    def tel_period(self):
        return config.backend.tel_period

    @property
    def bat_period(self):
        return config.backend.bat_period

    @property
    def pwmt_period(self):
        return config.backend.pwmt_period

    @property
    def pol_period(self):
        return config.backend.pol_period

    @property
    def bak_period(self):
        return config.backend.bak_period

    @property
    def tel_timeout(self):
        return config.backend.tel_timeout

    async def enable(self):
        if self.company == "company":
            logger.error("Backend not configured")
            return False
        config.create_default_hostname()
        await self.backup.start()
        current_tel = await self.backup.get_current()
        if current_tel:
            self.server.gw_manager.node_data.tel_data = current_tel
        if self.tel_period:
            self.tel_task = periodic_task(self.send_telemetry, self.tel_period)
        if self.bat_period:
            self.bat_task = periodic_task(self.send_battery, self.bat_period)
        if self.pwmt_period:
            self.pwmt_task = periodic_task(self.send_pwmt, self.pwmt_period)
        if self.bak_period:
            self.bak_task = periodic_task(self.send_backup, self.bak_period)
        return True

    async def disable(self):
        if self.tel_task:
            self.tel_task.cancel()
        if self.bat_task:
            self.bat_task.cancel()
        if self.pwmt_task:
            self.pwmt_task.cancel()
        if self.bak_task:
            self.bak_task.cancel()
        return True

    async def save_state(self):
        await self.backup.save_current(
            self.server.gw_manager.node_data.tel_data)

    async def send_telemetry(self):
        tel_data = self.server.gw_manager.node_data.tel_data
        nodes_dataframe = []
        for mac, data in tel_data.items():
            tel_datetime = dt.fromtimestamp(data["datetime"])
            if tel_datetime > self.tel_last_sent:
                node_dataframe = {
                    "mac_address" : mac,
                    "datetime": tel_datetime.strftime("%d/%m/%Y %H:%M"),
                }
                if "temperature" in data:
                    node_dataframe["temperature"] = data["temperature"]
                if "humidity" in data:
                    node_dataframe["humidity"] = data["humidity"]
                if "pressure" in data:
                    node_dataframe["pressure"] = data["pressure"]
                if "rssi" in data:
                    node_dataframe["rssi"] = data["rssi"]
                nodes_dataframe.append(node_dataframe)
        if not nodes_dataframe:
            logger.debug("No telemetry data to send")
            return
        self.tel_last_sent = dt.utcnow()
        body = {
            "device_id": self.device_id,
            "datetime": self.tel_last_sent.strftime("%d/%m/%Y %H:%M"),
            "schema_id": DataframeSchemaId.TELEMETRY_SCHEMA_ID,
            "data": nodes_dataframe,
        }
        url = f"{self.url}{self.slug}/data/push/"
        rsp = await self.http.request("backend_tel", "POST", url, body)
        if rsp is None or rsp.status_code >= 500:
            datetime_is_sync = await utils.ntp_is_sync()
            if datetime_is_sync:
                await self.backup.put(body)

    async def send_battery(self):
        bat_data = self.server.gw_manager.node_data.bat_data
        nodes_dataframe = []
        for mac, data in bat_data.items():
            bat_timestamp = dt.fromtimestamp(data["bat_timestamp"])
            if bat_timestamp > self.bat_last_sent:
                node_dataframe = {
                    "mac_address" : mac,
                    "bat_timestamp": bat_timestamp.strftime("%d/%m/%Y %H:%M"),
                    "battery": data["battery"],
                }
                nodes_dataframe.append(node_dataframe)
        if not nodes_dataframe:
            logger.debug("No battery data to send")
            return
        url = f"{self.url}{self.slug}/core/update-sensors-batteries/"
        self.bat_last_sent = dt.utcnow()
        body = {
            "data": nodes_dataframe,
        }
        await self.http.request("backend_bat", "POST", url, body)

    async def get_datacenter_id(self):
        url = f"{self.url}{self.slug}/core/info-gateways/"
        params = {"device_id": self.device_id}
        rsp = await self.http.request("backend_datacenter", "GET", url,
            None, params)
        if rsp is not None and rsp.ok:
            self.datacenter_id = rsp.json()["results"]["datacenter"]["id"]
            return True
        return False

    async def send_pwmt(self):
        pwmt_data = self.server.gw_manager.node_data.pwmt_data
        nodes_dataframe = []
        for mac, data in pwmt_data.items():
            pwmt_datetime = dt.fromtimestamp(data["datetime"])
            if pwmt_datetime > self.pwmt_last_sent:
                pwmt_datetime_str = pwmt_datetime.strftime("%d/%m/%Y %H:%M")
                node_dataframe = data.copy()
                node_dataframe["mac_address"] = mac
                node_dataframe["datetime"] = pwmt_datetime_str
                nodes_dataframe.append(node_dataframe)
        if not nodes_dataframe:
            logger.debug("No power data data to send")
            return
        self.pwmt_last_sent = dt.utcnow()
        body = {
            "device_id": self.device_id,
            "datetime": self.pwmt_last_sent.strftime("%d/%m/%Y %H:%M"),
            "schema_id": DataframeSchemaId.POWER_SCHEMA_ID,
            "data": nodes_dataframe,
        }
        url = f"{self.url}{self.slug}/data/push/"
        rsp = await self.http.request("backend_pwmt", "POST", url, body)
        if rsp is None or rsp.status_code >= 500:
            datetime_is_sync = await utils.ntp_is_sync()
            if datetime_is_sync:
                await self.backup.put(body)

    async def send_backup(self):
        url = f"{self.url}{self.slug}/data/push/"
        while self.backup.pending():
            body = await self.backup.get()
            if body is None:
                await self.backup.pop()
                continue
            rsp = await self.http.request("backend_bak", "POST", url, body)
            if rsp is not None:
                await self.backup.pop()
                logger.info("Backup [%s] pop (%d left)", body["datetime"],
                    len(self.backup))
            else:
                break

    async def unknown_node_handler(self, event):
        if not self.server.gateway.is_started():
            return
        mac = event.data["mac"]
        if mac in self.last_download_attempt:
            elapsed_time = dt.utcnow() - self.last_download_attempt[mac]
            if elapsed_time < self.DOWNLOAD_NODE_TIMEOUT:
                return
        if not self.datacenter_id:
            if not await self.get_datacenter_id():
                logger.debug("Unable to get datacenter_id")
                return
        self.last_download_attempt[mac] = dt.utcnow()
        url = (f"{self.url}{self.slug}/core/datacenters/"
            + f"{self.datacenter_id}/sensors/?search={mac}")
        rsp = await self.http.request("backend_new_node", "GET", url)
        if rsp is not None and rsp.ok and rsp.json()["results"]:
            for n in rsp.json()["results"]:
                if n["mac_address"] == mac:
                    if (not n["mesh_uuid"]
                            or not n["device_key"]
                            or not n["unicast_address"]):
                        logger.warning(f"New node {mac} is missing fields")
                        return

                    node = Node(bytes.fromhex(mac),
                        bytes.fromhex(n["mesh_uuid"]),
                        n["unicast_address"],
                        n["name"],
                        bytes.fromhex(n["device_key"]))
                    self.server.gateway.clear_replay_cache(node.unicast_addr)
                    await asyncio.to_thread(self.server.node_db.store_node,
                        node)
                    logger.info(f"New node {mac} saved")
                    return
        logger.warning(f"New node {mac} not found in backend")
        if rsp:
            logger.warning(f"Response: {rsp.json()}")

    async def get_nodes(self):
        # Get gateway info
        url = f"{self.url}{self.slug}/core/info-gateways/"
        params = {"device_id": self.device_id}
        rsp = await self.http.request("backend_gw_info", "GET", url,
            None, params)
        if rsp is not None and rsp.ok:
            gw = rsp.json()["results"]
            self.datacenter_id = gw["datacenter"]["id"]
            if not isinstance(gw["unicast_address"], int):
                logger.error("Invalid unicast address")
                return
            self.server.node_db.set_address(gw["unicast_address"])
            self.server.node_db.set_netkey(bytes.fromhex(gw["mesh"]["netkey"]))
        else:
            logger.error("Unable to get gateway info")
            return

        # Get nodes
        url = f"{self.url}{self.slug}/core/datacenters/{self.datacenter_id}" + \
            "/sensors/?page_size=50"
        while True:
            rsp = await self.http.request("backend_sensors", "GET", url)
            if rsp is not None and rsp.ok:
                rsp = rsp.json()
                for n in rsp["results"]:
                    try:
                        mac = bytes.fromhex(n["mac_address"])
                        uuid = bytes.fromhex(n["mesh_uuid"])
                        address = n["unicast_address"]
                        if not isinstance(address, int):
                            raise TypeError
                        name = n["name"]
                        devkey = bytes.fromhex(n["device_key"])
                    except ValueError:
                        logger.warning(f"Node {n['mac_address']} has " + \
                            "invalid mac address")
                        continue
                    except (KeyError, TypeError):
                        logger.warning(f"Node {n['mac_address']} has " + \
                            "invalid or missing fields")
                        continue

                    node = Node(mac, uuid, address, name, devkey)
                    self.server.node_db.store_node(node)

                if rsp["pagination"]["next"] is None:
                    break
                url = rsp["pagination"]["next"]
                url = url.replace("http:", "https:") #TODO: Remove when fixed
            else:
                logger.error("Unable to get node list")
                break


class DataframeSchemaId:
    TELEMETRY_SCHEMA_ID = "temp"
    POWER_SCHEMA_ID     = "power"
