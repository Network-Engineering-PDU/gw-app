import logging
from datetime import datetime as dt

from ttgateway import http_helper
from ttgateway.config import config
from ttgateway.utils import periodic_task


logger = logging.getLogger(__name__)


class AirQualityApp:
    def __init__(self, server):
        self.server = server
        self.handlers = []
        self.http = http_helper.HttpHelper(self.url, self.user, self.password)
        self.tel_task = None
        self.bat_task = None
        self.iaq_task = None
        self.tel_last_sent = dt.fromtimestamp(0)
        self.bat_last_sent = dt.fromtimestamp(0)
        self.iaq_last_sent = dt.fromtimestamp(0)

    @property
    def url(self):
        return config.air_quality.url

    @property
    def client(self):
        return config.air_quality.client

    @property
    def user(self):
        return config.air_quality.user

    @property
    def password(self):
        return config.air_quality.password

    @property
    def tel_period(self):
        return config.air_quality.tel_period

    @property
    def iaq_period(self):
        return config.air_quality.iaq_period

    @property
    def bat_period(self):
        return config.air_quality.bat_period

    @property
    def data_timeout(self):
        return config.air_quality.data_timeout

    @property
    def device_id(self):
        return config.backend.device_id

    async def enable(self) -> bool:
        if self.tel_period:
            self.tel_task = periodic_task(self.send_telemetry, self.tel_period)
        if self.iaq_period:
            self.iaq_task = periodic_task(self.send_iaq, self.iaq_period)
        if self.bat_period:
            self.bat_task = periodic_task(self.send_battery, self.bat_period)
        return True

    async def disable(self) -> bool:
        if self.tel_task:
            self.tel_task.cancel()
        if self.iaq_task:
            self.iaq_task.cancel()
        if self.bat_task:
            self.bat_task.cancel()
        return True

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
            "client": self.client,
            "device_id": self.device_id,
            "datetime": self.tel_last_sent.strftime("%d/%m/%Y %H:%M"),
            "data": nodes_dataframe,
        }
        url = f"{self.url}/data/push/telemetry/"
        await self.http.request("air_tel", "POST", url, body)

    async def send_iaq(self):
        iaq_data = self.server.gw_manager.node_data.iaq_data
        co2_data = self.server.gw_manager.node_data.co2_data
        iaq_co2_data = iaq_data.copy()
        for mac, value in co2_data.items():
            if mac in iaq_co2_data:
                iaq_co2_data[mac].update(value)
            else:
                iaq_co2_data[mac] = value
        nodes_dataframe = []
        for mac, data in iaq_co2_data.items():
            iaq_datetime = dt.fromtimestamp(data["datetime"])
            if iaq_datetime > self.iaq_last_sent:
                iaq_datetime_str = iaq_datetime.strftime("%d/%m/%Y %H:%M")
                node_dataframe = data.copy()
                node_dataframe["mac_address"] = mac
                node_dataframe["datetime"] = iaq_datetime_str
                nodes_dataframe.append(node_dataframe)
        if not nodes_dataframe:
            logger.debug("No telemetry data to send")
            return
        self.iaq_last_sent = dt.utcnow()
        body = {
            "client": self.client,
            "device_id": self.device_id,
            "datetime": self.tel_last_sent.strftime("%d/%m/%Y %H:%M"),
            "data": nodes_dataframe,
        }
        url = f"{self.url}/data/push/co2/"
        await self.http.request("air_iaq", "POST", url, body)

    async def send_battery(self):
        bat_data = self.server.gw_manager.node_data.bat_data
        nodes_dataframe = []
        for mac, data in bat_data.items():
            bat_timestamp = dt.fromtimestamp(data["bat_timestamp"])
            if bat_timestamp > self.bat_last_sent:
                bat_timestamp_str = bat_timestamp.strftime("%d/%m/%Y %H:%M")
                node_dataframe = {
                    "mac_address" : mac,
                    "battery": data["battery"],
                    "bat_timestamp": bat_timestamp_str,
                }
                nodes_dataframe.append(node_dataframe)
        if not nodes_dataframe:
            logger.debug("No telemetry data to send")
            return
        self.bat_last_sent = dt.utcnow()
        url = f"{self.url}/core/update-sensors-batteries/"
        body = {
            "data": nodes_dataframe,
        }
        await self.http.request("air_bat", "POST", url, body)
