import logging

from ttgwlib import ConfigPassthrough

from ttgateway.gateway.common import GatewayCommon
from ttgateway.config import config
import ttgateway.commands as cmds

logger = logging.getLogger(__name__)

class GatewayLocal(GatewayCommon):
    """ GatewayLocal manager local gateway operations and passthrough
    configurations.

    This class extends `GatewayCommon` to handle local gateway operations,
    including starting and stopping passthrough communication.
    """
    def init(self, platform, port):
        """ Initializes the gateway with the specified platform and port.

        :param platform: The platform to initialize.
        :type platform: str or :class:`~ttgwlib.platform.board.Platform`

        :param port: For heimdall or desktop platform, manually selects
            microcontrollervport. If left to None, the port will be selected
            automatically. For cloud platform, this must be the network socket.
        :type port: str or socket.socket
        """
        self.gw.init(platform, port)

    def check(self):
        """ Performs a hardware check on the gateway.
        """
        self.gw.hw_check()

    def start_passthrough(self, address: str, tcp_port: int, ca_cert: str,
            client_cert: str, client_key: str):
        """ Starts passthrough communication with the specified configuration.

        :param address: The remote server's address.
        :type address: str

        :param tcp_port: The remote server's TCP port.
        :type tcp_port: integer

        :param ca_cert: The path to the CA certificate file.
        :type ca_cert: str

        :param client_cert: The path to the client certificate file.
        :type client_cert: str

        :param client_key: The path to the client private key file.
        :type client_key: str
        """
        passthrough_config = ConfigPassthrough(address, tcp_port, ca_cert,
            client_cert, client_key, config.backend.device_id)
        self.gw.start_passthrough(passthrough_config)
        self.gw.add_event_handler(self.event_handler.process_event)
        self.gw_started = True

    def stop_passthrough(self):
        """ Stops passthrough communication and removes the event handler.
        """
        self.gw.remove_event_handler(self.event_handler.process_event)
        self.gw.stop()
        self.gw_started = False

    async def dispatch(self, command) -> cmds.Response:
        """ Dispatches a command to the gateway.

        :param command: The command to dispatch.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response from the command.
        :rtype: class:`~ttgateway.commands.Response`
        """
        logger.debug(f"Command received: {type(command).__name__}")
        return await super().dispatch(command)

    def is_passthrough_connected(self):
        """ Checks if the passthrough communication is currently connected.

        :return: True if the passthrough is connected, False otherwise.
        :rtype: bool
        """
        return self.gw.is_passthrough_connected()
