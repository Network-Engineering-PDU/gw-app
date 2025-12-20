import logging

from ttgateway.network_helper import NetworkHelper
from ttgateway.http_helper import HttpHelper
from ttgateway.config import config


logger = logging.getLogger(__name__)


class FaultBackendHelper:
    """ Provides helper functions for interacting with the fault backend API.
    """
    def __init__(self, fault_mngr):
        """ Initializes the FaultBackendHelper with a fault manager instance.

        :param fault_mngr: The fault manager instance that this helper will work
            with.
        :type fault_mngr:
            class:`~ttgateway.fault_tolerance.fault_manager.FaultManager`
        """
        self.fault_mngr = fault_mngr
        self.http = HttpHelper(self.url, self.user, self.password)

    @property
    def url(self):
        """ Returns the backend URL configured in the system configuration.

        :return: The backend URL.
        :rtype: str
        """
        return config.backend.url

    @property
    def device_id(self):
        """ Returns the device ID configured in the system configuration.

        :return: The device ID.
        :rtype: str
        """
        return config.backend.device_id

    @property
    def user(self):
        """ Returns the user configured in the system configuration.

        :return: The user.
        :rtype: str
        """
        return config.backend.user

    @property
    def password(self):
        """ Returns the password configured in the system configuration.

        :return: The password.
        :rtype: str
        """
        return config.backend.password

    async def get_gateway(self, datacenter_id, gw_id):
        """ Retrieves gateway information from the backend.

        :param datacenter_id: The ID of the datacenter.
        :type datacenter_id: str

        :param gw_id: The ID of the gateway.
        :type gw_id: str

        :return: The response from the backend API.
        :rtype: class:`requests.models.Response`
        """
        url = f"{self.url}/core/datacenters/{datacenter_id}/gateways/{gw_id}/"
        return await self.http.request("fault_get_gw", "GET", url, None)

    async def patch_gateway(self, datacenter_id, gw_id, gateway):
        """ Updates gateway information in the backend.

        :param datacenter_id: The ID of the datacenter.
        :type datacenter_id: str

        :param gw_id: The ID of the gateway.
        :type gw_id: str

        :param gateway: The gateway data to update.
        :type gateway: dict

        :return: The response from the backend API.
        :rtype: class:`requests.models.Response`
        """
        url = f"{self.url}/core/datacenters/{datacenter_id}/gateways/{gw_id}/"
        return await self.http.request("fault_patch_gw", "PATCH", url, gateway)

    async def get_gateway_info(self, device_id):
        """ Retrieves information about a specific gateway from the backend.

        :param device_id: The device ID of the gateway.
        :type device_id: str

        :return: The response from the backend API.
        :rtype: class:`requests.models.Response`
        """
        url = f"{self.url}/core/info-gateways/"
        params = {"device_id": device_id}
        return await self.http.request("fault_gw_info", "GET", url, None,
            params)

    async def update_gateway_info(self):
        """ Updates the gateway information in the backend with current details.

        :return: True if the update was successful, False otherwise.
        :rtype: bool
        """
        # Get datacenter and gateway id
        rsp = await self.get_gateway_info(self.device_id)
        if rsp is None:
            logger.error("Downloading gateway info failed. Not found")
            return False
        if not rsp.ok:
            logger.error(f"Downloading gateway info failed. {rsp.json()}")
            return False
        try:
            datacenter_id = rsp.json()["results"]["datacenter"]["id"]
            gateway_id = rsp.json()["results"]["id"]
        except KeyError:
            logger.error("Invalid gateway data")
            return False
        # Get gateway
        rsp = await self.get_gateway(datacenter_id, gateway_id)
        if rsp is None:
            logger.error("Downloading gateway failed. Not found.")
            return False
        if not rsp.ok:
            logger.error(f"Downloading gateway failed: {rsp.json()}")
            return False
        # Set gateway
        data = rsp.json()
        network_data = await NetworkHelper.get_network_data()
        gateway = {
            "mesh_id": data["mesh"]["id"],
            "device_id": data["device_id"],
            "name": data["name"],
            "x": data["x"],
            "y": data["y"],
            "z": data["z"],
            "room_id":  data["room"]["id"],
            "row_id": data["row"]["id"],
            "rack_id":  data["rack"]["id"],
            "unit": data["unit"],
            "type": data["type"],
            "configuration": {
                "mask": network_data.mask,
                "dns_1": data["configuration"]["dns_1"],
                "dns_2": data["configuration"]["dns_2"],
                "gateway": network_data.gateway,
                "ip_address": network_data.ip
            }
        }
        rsp = await self.patch_gateway(datacenter_id, gateway_id, gateway)
        if rsp is None:
            logger.error("Updating gateway failed. Not found.")
            return False
        if not rsp.ok:
            logger.error(f"Updating gateway failed. {rsp.json()}")
            return False
        return True

    async def get_cluster(self):
        """ Retrieves the cluster information and updates the fault manager's
        cluster.

        :return: True if the cluster was successfully retrieved and updated,
        False otherwise.
        :rtype: bool
        """
        rsp = await self.get_gateway_info(self.device_id)
        if rsp is None:
            logger.error("Downloading cluster failed. Not found.")
            return False
        if not rsp.ok:
            logger.error(f"Downloading cluster failed. {rsp.json()}")
            return False
        if self.fault_mngr.transport not in ("bt-mesh", "udp"):
            logger.error(f"Invalid transport type: {self.fault_mngr.transport}")
            return False
        try:
            data = rsp.json()["results"]
            if self.fault_mngr.transport == "bt-mesh":
                self.fault_mngr.node_id = data["unicast_address"]
            elif self.fault_mngr.transport == "udp":
                self.fault_mngr.node_id = data["configuration"]["ip_address"]
            device_cluster = data["mesh"]["gateways"]
        except KeyError:
            logger.error("Invalid gateway backend configuration")
            return False
        cluster = [self.fault_mngr.node_id]
        for device in device_cluster:
            if device == self.device_id.lower():
                continue
            rsp = await self.get_gateway_info(device)
            if rsp is None:
                logger.error("Downloading cluster failed. Not found.")
                return False
            if not rsp.ok:
                logger.error(f"Downloading cluster failed. {rsp.json()}")
                return False
            try:
                if self.fault_mngr.transport == "bt-mesh":
                    addr = rsp.json()["results"]["unicast_address"]
                elif self.fault_mngr.transport == "udp":
                    addr = rsp.json()["results"]["configuration"]["ip_address"]
                else:
                    logger.error("Invalid fault transport layer")
                    return False
            except KeyError:
                logger.error("Invalid gateway backend configuration")
                return False
            cluster.append(addr)
        self.fault_mngr.cluster = cluster
        return True
