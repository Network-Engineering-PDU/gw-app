import logging

from ttgateway.gateway.common import GatewayCommon
import ttgateway.commands as cmds


logger = logging.getLogger(__name__)


class GatewayRemote(GatewayCommon):
    """ GatewayRemote manages remote gateway operations and configurations.

    This class extends `GatewayCommon` to handle additional operations
    specific to remote gateways.
    """
    async def dispatch(self, command) -> cmds.Response:
        logger.debug(f"Command received: {type(command).__name__}")
        return await super().dispatch(command)

    def __init__(self, event_handler, node_db, gw_id, gw_version, platform,
            config_cb=None):
        """ Initializes a GatewayRemote instance.

        :param event_handler: An event handler to manage gateway events.
        :type event_handler: class:`~ttgateway.event_handler.EventHandler`

        :param node_db: A database interface for node data.
        :type node_db: class:`~ttgateway.gateway.sqlite_database.SqliteDatabase`
            or `~ttgateway.gateway.memory_database.MemoryDatabase`

        :param gw_id: Identifier for the gateway.
        :type gw_id: str

        :param gw_version: Version of the gateway.
        :type gw_version: str

        :param platform: Platform of the gateway.
        :type platform: str or :class:`~ttgwlib.platform.board.Platform`

        :param config_cb: Optional callback function for additional
            configuration.
        :type config_cb: Callable, optional
        """
        super().__init__(event_handler, node_db, gw_id, config_cb)
        self.gw_version = gw_version
        self.gw_platform = platform

    @property
    def platform(self):
        """ Gets the platform for the gateway.

        :return: The platform.
        :rtype: str or :class:`~ttgwlib.platform.board.Platform`
        """
        return self.gw_platform

    @property
    def version(self):
        """ Gets the version of the gateway software.

        :return: The version.
        :rtype: str
        """
        return self.gw_version

    def close(self):
        """ Closes the gateway's UART socket connection.
        """
        self.gw.uart.socket.close()
