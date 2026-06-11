
import ipaddress
import re

from ttgateway import utils
from ttgateway.config import config

class NetworkHelper:
    WIFI_CONN = "ble-wifi-conn"
    ETH_CONN = "ble-eth-conn"

    @classmethod
    async def get_network_data(cls) -> 'NetworkData':
        platform = config.gateway.platform
        if platform in ("heimdall", "heimdall_v1", "heimdall_v2"):
            return await cls.get_network_data_heimdall()
        return await cls.get_network_data_desktop()

    @classmethod
    async def _get_ip_from_if(cls, iface):
        ip, mask, gateway = None, None, None
        _, output = await utils.shell(f"nmcli -t d show {iface}")
        for l in output.split("\n"):
            if "IP4.ADDRESS[1]" in l:
                ip = l.split(":",1)[1].strip()
            if "IP4.GATEWAY" in l:
                gateway = l.split(":",1)[1].strip()
        iface_ip = ipaddress.IPv4Interface(ip)
        ip = str(iface_ip.ip)
        mask = str(iface_ip.netmask)
        return NetworkData(ip=ip, mask=mask, gateway=gateway)

    @classmethod
    async def get_network_data_heimdall(cls) -> 'NetworkData':
        retval, output = await utils.shell(f"nmcli -t con show {cls.ETH_CONN}")
        if retval == 0: # Static ethernet is configured
            nw_type = NetworkType.ETH_STATIC
            retval, output = await utils.shell(
                f"nmcli -t -f GENERAL.STATE con show {cls.ETH_CONN}")
            if "activated" in output:
                iface = NetworkType.to_interface(nw_type)
                return await cls._get_ip_from_if(iface)
        retval, output = await utils.shell(f"nmcli -t con show {cls.WIFI_CONN}")
        if retval == 0: # Wifi is configured
            nw_type = NetworkType.WIFI
            retval, output = await utils.shell(
                f"nmcli -t -f GENERAL.STATE con show {cls.WIFI_CONN}")
            if "activated" in output:
                iface = NetworkType.to_interface(nw_type)
                return await cls._get_ip_from_if(iface)
        # In other cases the connection is dhcp
        nw_type = NetworkType.ETH_DHCP
        iface = NetworkType.to_interface(nw_type)
        retval, output = await utils.shell(
            f"nmcli -t -f GENERAL.STATE d show {iface}")
        if "connected" in output:
            return await cls._get_ip_from_if(iface)
        return NetworkData(ip=None, mask=None, gateway=None)

    @classmethod
    async def get_network_data_desktop(cls) -> 'NetworkData':
        retval, output = await utils.shell("ip route")
        if retval != 0 or output is None:
            return
        match = re.search("default via ([\d\.]+)", output)
        if match:
            gateway = match.group(1)
            network = ".".join(gateway.split(".")[:-1] + ["0"])
            match = re.search(f"({network}/\d+) [\w0 ]+ ([\d\.]+)", output)
            if match:
                mask = str(ipaddress.IPv4Interface(match.group(1)).netmask)
                ip = match.group(2)
                return NetworkData(ip=ip, mask=mask, gateway=gateway)
        return NetworkData(ip=None, mask=None, gateway=None)


class NetworkType:
    UNCONF     = 1
    ETH_DHCP   = 2
    ETH_STATIC = 3
    WIFI       = 4
    LTE_4G     = 5

    @classmethod
    def get_interfaces(cls):
        return ["wwan0", "ppp0", "wlan0", "eth0", "eth1"]

    @classmethod
    def from_interface(cls, interface):
        if interface == "ppp0" or interface == "wwan0":
            return cls.LTE_4G
        if interface == "wlan0":
            return cls.WIFI
        if interface == "eth0" or interface == "eth1":
            return cls.ETH_DHCP
        return cls.UNCONF

    @classmethod
    def get_static(cls, network_type):
        if network_type == cls.ETH_DHCP:
            return cls.ETH_STATIC
        return network_type

    @classmethod
    def is_static(cls, network_type):
        if network_type == cls.ETH_STATIC:
            return True
        return False

    @classmethod
    def to_interface(cls, network_type, eth_interface="eth0"):
        """Return interface name for network type.
        
        Args:
            network_type: Type of network connection
            eth_interface: Ethernet interface to use (eth0 or eth1). Default: eth0
        
        Returns:
            Interface name (eth0, eth1, wlan0, ppp0, etc.)
        """
        if network_type == cls.ETH_DHCP or network_type == cls.ETH_STATIC:
            return eth_interface
        if network_type == cls.WIFI:
            return "wlan0"
        if network_type == cls.LTE_4G:
            return "ppp0"
        return "unknown_if"


class NetworkData:
    def __init__(self, ip, mask, gateway):
        self.ip = ip
        self.mask = mask
        self.gateway = gateway
