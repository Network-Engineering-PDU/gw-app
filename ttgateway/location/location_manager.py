import logging
import ttgateway.commands as cmds
from ttgateway.location.location_helper import LocationHelper

logger = logging.getLogger(__name__)

class LocationManager:
    def __init__(self):
        self.location_helper = LocationHelper()

    async def process_command(self, command):
        logger.debug(f"Command received: {type(command).__name__}")
        if isinstance(command, cmds.LocationGetGenesis):
            return await self.location_helper.get_genesis(command)

        if isinstance(command, cmds.LocationPostGenesis):
            return await self.location_helper.post_genesis(command)

        if isinstance(command, cmds.LocationSaveGenesis):
            return self.location_helper.save_genesis(command)

        if isinstance(command, cmds.LocationListDatacenters):
            return self.location_helper.list_datacenters(command)

        if isinstance(command, cmds.LocationListRooms):
            return self.location_helper.list_rooms(command)

        if isinstance(command, cmds.LocationListRows):
            return self.location_helper.list_rows(command)

        if isinstance(command, cmds.LocationListContainers):
            return self.location_helper.list_containers(command)

        if isinstance(command, cmds.LocationListRacks):
            return self.location_helper.list_racks(command)

        if isinstance(command, cmds.LocationListGateways):
            return self.location_helper.list_gateways(command)

        if isinstance(command, cmds.LocationListNodes):
            return self.location_helper.list_nodes(command)

        if isinstance(command, cmds.LocationMoveGlobal):
            return self.location_helper.move_global(command)

        if isinstance(command, cmds.LocationMoveRow):
            return self.location_helper.move_row(command)

        if isinstance(command, cmds.LocationMoveContainer):
            return self.location_helper.move_container(command)

        if isinstance(command, cmds.LocationMoveRack):
            return self.location_helper.move_rack(command)

        if isinstance(command, cmds.LocationMoveGateway):
            return self.location_helper.move_gateway(command)

        if isinstance(command, cmds.LocationMoveNode):
            return self.location_helper.move_node(command)

        if isinstance(command, cmds.LocationAddRoom):
            return self.location_helper.add_room(command)

        if isinstance(command, cmds.LocationAddRow):
            return self.location_helper.add_row(command)

        if isinstance(command, cmds.LocationAddContainer):
            return self.location_helper.add_container(command)

        if isinstance(command, cmds.LocationAddRack):
            return self.location_helper.add_rack(command)

        if isinstance(command, cmds.LocationAddGateway):
            return self.location_helper.add_gateway(command)

        if isinstance(command, cmds.LocationAddNode):
            return self.location_helper.add_node(command)

        if isinstance(command, cmds.LocationDelRoom):
            return self.location_helper.del_room(command)

        if isinstance(command, cmds.LocationDelRow):
            return self.location_helper.del_row(command)

        if isinstance(command, cmds.LocationDelContainer):
            return self.location_helper.del_container(command)

        if isinstance(command, cmds.LocationDelRack):
            return self.location_helper.del_rack(command)

        if isinstance(command, cmds.LocationDelGateway):
            return self.location_helper.del_gateway(command)

        if isinstance(command, cmds.LocationDelNode):
            return self.location_helper.del_node(command)

        if isinstance(command, cmds.LocationImportRoom):
            return self.location_helper.import_room(command)

        if isinstance(command, cmds.LocationImportGenesis):
            return self.location_helper.import_genesis(command)
