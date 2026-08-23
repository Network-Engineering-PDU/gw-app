import unittest
from unittest.mock import AsyncMock, patch

from ttgateway.network_helper import NetworkHelper


class NetworkHelperTest(unittest.IsolatedAsyncioTestCase):

    async def test_bridge_profile_reads_address_from_active_bridge_device(self):
        responses = [
            (0, "ble-eth-conn\n"),
            (0, "GENERAL.STATE:activated\n"),
            (0, "ble-eth-conn:br0\n"),
            (
                0,
                "IP4.ADDRESS[1]:192.168.1.100/24\n"
                "IP4.GATEWAY:192.168.1.1\n",
            ),
        ]

        with patch(
            "ttgateway.network_helper.utils.shell",
            new=AsyncMock(side_effect=responses),
        ) as shell:
            network = await NetworkHelper.get_network_data_heimdall()

        self.assertEqual(network.ip, "192.168.1.100")
        self.assertEqual(network.mask, "255.255.255.0")
        self.assertEqual(network.gateway, "192.168.1.1")
        shell.assert_any_await(
            "nmcli -t -f NAME,DEVICE connection show --active"
        )
        shell.assert_any_await("nmcli -t d show br0")

    async def test_missing_interface_address_returns_empty_network_data(self):
        with patch(
            "ttgateway.network_helper.utils.shell",
            new=AsyncMock(return_value=(0, "IP4.GATEWAY:\n")),
        ):
            network = await NetworkHelper._get_ip_from_if("br0")

        self.assertIsNone(network.ip)
        self.assertIsNone(network.mask)


if __name__ == "__main__":
    unittest.main()
