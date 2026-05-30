import logging
from typing import Dict

import ttgateway.commands as cmds
from ttgateway.apps.backend import BackendApp
from ttgateway.apps.snmp import SnmpApp
from ttgateway.apps.air_quality import AirQualityApp
from ttgateway.apps.csv import CsvApp
from ttgateway.apps.net_eng import NetworkEngineeringApp
from ttgateway.apps.automation import AutomationApp
try:
    from ttgateway.apps.influx import InfluxApp
except ImportError:
    InfluxApp = None

try:
    from ttgateway.apps.mqtt import MQTTApp
except ImportError:
    MQTTApp = None


logger = logging.getLogger(__name__)


class AppManager:
    """ Manages the various application interfaces for the server.
    """
    def __init__(self, server):
        """ Initializes the AppManager with the given server.

        :param server: The server instance that this manager will operate on.
        :type server: class:`~ttgateway.server.Server`
        """
        self.server = server
        self.interfaces = {
            "backend": BackendApp(self.server),
            "air_quality": AirQualityApp(self.server),
            "snmp": SnmpApp(self.server),
            "csv": CsvApp(),
            "net_eng": NetworkEngineeringApp(self.server.node_db),
            "automation": AutomationApp(self.server),
        }
        if InfluxApp:
            self.interfaces["influx"] = InfluxApp()

        if MQTTApp:
            self.interfaces["mqtt"] = MQTTApp()

        self.paused = False
        self.enabled = set()
        self.enabled_paused = set()

    def interface_exists(self, interface: str) -> bool:
        """ Checks if a given interface exists in the manager.

        :param interface: The name of the interface to check.
        :type interface: str

        :return: True if the interface exists, False otherwise.
        :rtype: bool
        """
        return interface in self.interfaces

    def list_interfaces(self) -> Dict[str, str]:
        """ Lists the status of all interfaces managed by this instance.

        :return: A dictionary with interface names as keys and their statuses as
            values.
        :rtype: Dict[str, str]
        """
        interfaces = {}
        for ifc in self.interfaces:
            if ifc in self.enabled_paused:
                interfaces[ifc] = "paused"
            elif ifc in self.enabled:
                interfaces[ifc] = "enabled"
            else:
                interfaces[ifc] = "disabled"
        return interfaces

    async def enable_interface(self, interface: str) -> bool:
        """ Enables a specific interface. If the manager is paused, adds the
        interface to the paused enabled list.

        :param interface: The name of the interface to enable.
        :type interface: str

        :return: True if the interface was successfully enabled, otherwise
            False.
        :rtype: bool
        """
        if self.paused:
            self.enabled_paused.add(interface)
            return

        if interface not in self.enabled:
            await self.interfaces[interface].enable()
            for event_type, handler in self.interfaces[interface].handlers:
                self.server.event_handler.add_handler(event_type, handler)
            self.enabled.add(interface)

        if interface == "backend":
            self.server.virtual_manager.start_polling()

    async def disable_interface(self, interface: str):
        """ Disables a specific interface. If the manager is paused, removes the
        interface from the paused enabled list.

        :param interface: The name of the interface to disable.
        :type interface: str
        """
        if self.paused:
            self.enabled_paused.remove(interface)
            return

        if interface in self.enabled:
            await self.interfaces[interface].disable()
            for _, handler in self.interfaces[interface].handlers:
                self.server.event_handler.remove_handler(handler)
            self.enabled.remove(interface)

        if interface == "backend":
            self.server.virtual_manager.stop_polling()

    async def pause(self):
        """ Pauses the manager, disabling all enabled interfaces and storing
        their state for resumption.
        """
        if self.paused:
            return
        self.enabled_paused = self.enabled.copy()
        for interface in self.enabled_paused:
            await self.disable_interface(interface)
        self.paused = True

    async def resume(self):
        """ Resumes the manager, re-enabling all previously enabled but paused
        interfaces.
        """
        if not self.paused:
            return
        self.paused = False
        enabled_paused = self.enabled_paused.copy()
        for interface in enabled_paused:
            await self.enable_interface(interface)
        self.enabled_paused.clear()

    async def process_commands(self, command):
        """ Processes and executes the given command.

        :param command: The command to process.
        :type command: class:`~ttgateway.commands.Command`

        :return: The response based on the command processing result.
        :rtype: class:`~ttgateway.commands.Response`
        """
        logger.debug(f"Command received: {type(command).__name__}")
        if isinstance(command, cmds.AppListInterfaces):
            return command.response(extra_data=self.list_interfaces())

        if isinstance(command, cmds.AppEnableInterface):
            if not self.interface_exists(command.interface):
                return command.response("Unknown interface:"
                    + f"{command.interface}", False)
            await self.enable_interface(command.interface)
            return command.response("")

        if isinstance(command, cmds.AppDisableInterface):
            if not self.interface_exists(command.interface):
                return command.response("Unknown interface:"
                    + f"{command.interface}", False)
            await self.disable_interface(command.interface)
            return command.response("")

        if isinstance(command, cmds.AppSaveState):
            if "backend" in self.enabled:
                await self.interfaces["backend"].save_state()
            return command.response("")

        logger.warning("Unknown command")
        return command.response("Unknown command", False)
