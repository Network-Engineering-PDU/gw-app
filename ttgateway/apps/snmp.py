import asyncio
import json
import logging
import os

from ttgateway import utils
from ttgateway.config import config


logger = logging.getLogger(__name__)


class SnmpApp:
    def __init__(self, app_server):
        self.handlers = []
        self.data = {}
        self.app_server = app_server
        self.server = None

    async def enable(self):
        os.makedirs("/home/root/snmp", exist_ok=True)
        if not os.path.exists("/home/root/snmp/snmpd.conf"):
            retval, _ = await utils.shell(
                "cp /usr/share/ttsnmp/snmpd.conf /home/root/snmp/snmpd.conf")
            if retval != 0:
                logger.warning("Can not copy SNMP configuration file")
        retval, _ = await utils.shell("/etc/init.d/snmpd start", timeout=10)
        if retval != 0:
            return False
        self.server = await asyncio.start_unix_server(self.server_cb,
            path=config.SNMP_SOCKET)
        return True

    async def disable(self):
        retval, _ = await utils.shell("/etc/init.d/snmpd stop", timeout=10)
        if retval != 0:
            return False
        if self.server is not None and self.server.is_serving():
            self.server.close()
            await self.server.wait_closed()
        return True

    async def server_cb(self, reader, writer):
        tel_data = self.app_server.gw_manager.node_data.tel_data
        bat_data = self.app_server.gw_manager.node_data.bat_data
        power_data = self.app_server.gw_manager.node_data.pwmt_data
        data = tel_data.copy()
        for d in (bat_data, power_data):
            for mac, value in d.items():
                if mac in data:
                    data[mac].update(value)
                else:
                    data[mac] = value
        writer.write(json.dumps(data).encode())
        await writer.drain()
        writer.close()
