import logging
import socket

from ttgateway.config import config


logger = logging.getLogger(__name__)


def get_led_controller():
    if not config.is_loaded():
        config.read()
    platform = config.gateway.platform
    print(platform)
    if platform in ("heimdall", "heimdall_v1", "heimdall_v2"):
        return GpioModuleController
    if platform in ("cm_v1", "cm_v2"):
        return DummyGpioController
    return DummyGpioController


class DummyGpioController:
    @classmethod
    def status_started(cls):
        return

    @classmethod
    def status_stopped(cls):
        return

    @classmethod
    def link_connected(cls):
        return

    @classmethod
    def link_not_connected(cls):
        return

    @classmethod
    def mesh_rx(cls):
        return

    @classmethod
    def mesh_tx(cls):
        return

    @classmethod
    def bt_advertising(cls):
        return

    @classmethod
    def bt_connected(cls):
        return

    @classmethod
    def bt_disconnected(cls):
        return

    @classmethod
    def shield_power_off(cls):
        return

    @classmethod
    def shield_power_on(cls):
        return

    @classmethod
    def shield_reset(cls):
        return

    @classmethod
    def leds_off(cls):
        return


class GpioModuleController:
    SOCKET_PATH = '/tmp/gpio_module.socket'

    @classmethod
    def _send_cmd(cls, cmd):
        """Send command to socket"""
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client_socket.connect(cls.SOCKET_PATH)
            client_socket.send(cmd.encode())
            client_socket.close()
        except FileNotFoundError as ex:
            logger.debug(f"GPIO module socket not found: {str(ex)}")

    @classmethod
    def status_started(cls):
        cls._send_cmd('status_started')

    @classmethod
    def status_stopped(cls):
        cls._send_cmd('status_stopped')

    @classmethod
    def link_connected(cls):
        cls._send_cmd('link_connected')

    @classmethod
    def link_not_connected(cls):
        cls._send_cmd('link_not_connected')

    @classmethod
    def mesh_rx(cls):
        cls._send_cmd('mesh_rx')

    @classmethod
    def mesh_tx(cls):
        cls._send_cmd('mesh_tx')

    @classmethod
    def bt_advertising(cls):
        cls._send_cmd('bt_advertising')

    @classmethod
    def bt_connected(cls):
        cls._send_cmd('bt_connected')

    @classmethod
    def bt_disconnected(cls):
        cls._send_cmd('bt_disconnected')

    @classmethod
    def shield_power_off(cls):
        cls._send_cmd('shield_power_off')

    @classmethod
    def shield_power_on(cls):
        cls._send_cmd('shield_power_on')

    @classmethod
    def shield_reset(cls):
        cls._send_cmd('shield_reset')

    @classmethod
    def leds_off(cls):
        cls._send_cmd( 'leds_off')
