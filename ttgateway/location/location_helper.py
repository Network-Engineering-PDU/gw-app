import os
import json

from ttgateway.config import config
from ttgateway.http_helper import HttpHelper


RACK_TYPE = {
    "IT":            1,
    "REFRIGERATION": 2,
    "NONE":          3
}

NODE_SOURCE = {
    "INLET":   1,
    "OUTLET":  2,
    "SUPPLY":  3,
    "RETURN":  4,
    "AMBIENT": 5,
    "FLOOR":   6,
    "GRID":    7,
}


class LocationHelper:
    def __init__(self):
        self.http = HttpHelper(self.url, self.user, self.password)
        self.file = os.path.join(config.TT_DIR, "genesis.json")
        self.genesis = None

    @property
    def url(self):
        return config.backend.url

    @property
    def company(self):
        return config.backend.company

    @property
    def slug(self):
        return "" # f"/{self.company}" if multi-database; "" if single-database

    @property
    def device_id(self):
        return config.backend.device_id

    @property
    def user(self):
        return config.backend.user

    @property
    def password(self):
        return config.backend.password

    async def get_genesis(self, command):
        url = f"{self.url}{self.slug}/core/genesis/"
        r = await self.http.request("get_genesis", "GET", url)
        if r is not None and r.ok and r.json()["results"]:
            self.genesis = r.json()["results"]
            return command.response("Genesis successfully downloaded")
        return command.response("Genesis not found in backend")

    async def post_genesis(self, command):
        url = f"{self.url}{self.slug}/core/genesis/"
        body = self.genesis
        r = await self.http.request("post_genesis", "POST", url, body,
                timeout=30)
        if r is not None and r.ok:
            return command.response("Genesis successfully uploaded")
        return command.response("Genesis uploading failed")

    def save_genesis(self, command):
        if self.genesis is not None:
            with open(self.file, "w") as f:
                f.write(json.dumps(self.genesis, indent=4))
            return command.response("Genesis successfully saved")
        return command.response("Genesis not found")

    def list_datacenters(self, command):
        if self.genesis is not None:
            return command.response("",
                    extra_data={"datacenters": self.genesis["datacenters"]})
        return command.response("Genesis not found")

    def list_rooms(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    return command.response("",
                            extra_data={"rooms": datacenter["rooms"]})
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def list_rows(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            rows = room["rows"]
                            return command.response("",
                                    extra_data={"rows": rows})
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def list_containers(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            try:
                                containers = room["containers"]
                                return command.response("",
                                        extra_data={"containers": containers})
                            except KeyError:
                                return command.response("Deprecated genesis")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def list_racks(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if command.row:
                                for row in room["rows"]:
                                    if row["name"] == command.row:
                                        racks = row["racks"]
                                        return command.response("",
                                                extra_data={"racks": racks})
                                return command.response("Row not found")
                            racks = []
                            for row in room["rows"]:
                                for rack in row["racks"]:
                                    racks.append(rack)
                            return command.response("",
                                    extra_data={"racks": racks})
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def list_gateways(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            try:
                                gateways = room["gateways"]
                                return command.response("",
                                        extra_data={"gateways": gateways})
                            except KeyError:
                                return command.response("Deprecated genesis")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def list_nodes(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if command.row:
                                for row in room["rows"]:
                                    if row["name"] == command.row:
                                        nodes = []
                                        for rack in row["racks"]:
                                            for node in rack["sensors"]:
                                                nodes.append(node)
                                        return command.response("",
                                                extra_data={"nodes": nodes})
                                return command.response("Row not found")
                            if command.rack:
                                for row in room["rows"]:
                                    for rack in row["racks"]:
                                        if rack["name"] == command.rack:
                                            nodes = []
                                            for node in rack["sensors"]:
                                                nodes.append(node)
                                            return command.response("",
                                                extra_data={"nodes": nodes})
                                    return command.response("Rack not found")
                            else:
                                nodes = []
                                for row in room["rows"]:
                                    for rack in row["racks"]:
                                        for node in rack["sensors"]:
                                            nodes.append(node)
                                return command.response("",
                                        extra_data={"nodes": nodes})
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def move_global(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "gateways" in room: # Only if old genesis
                                for gateway in room["gateways"]:
                                    gateway["x"] += command.disx
                                    gateway["y"] += command.disy
                            if "containers" in room: # Only if old genesis
                                for container in room["containters"]:
                                    container["x_center"] += command.disx
                                    container["y_center"] += command.disy
                            for row in room["rows"]:
                                if "cold_pos" in row and not None in \
                                        (row["cold_pos"], row["hot_pos"]):
                                    if row["is_horizontal"]:
                                        row["cold_pos"] += command.disy
                                        row["hot_pos"] += command.disy
                                    else:
                                        row["cold_pos"] += command.disx
                                        row["hot_pos"] += command.disx
                                for rack in row["racks"]:
                                    if "x_center" in row and not None in \
                                            (rack["x_center"],rack["y_center"]):
                                        rack["x_center"] += command.disx
                                        rack["y_center"] += command.disy
                                    for node in rack["sensors"]:
                                        if not None in (node["x"], node["y"]):
                                            node["x"] += command.disx
                                            node["y"] += command.disy
            rsp = f"{command.room} moved X:{command.disx},Y:{command.disy}"
            return command.response(rsp)
        return command.response("Genesis not found")

    def move_row(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                if row["name"] == command.row:
                                    if ("cold_pos" in row
                                            and None not in (row["cold_pos"],
                                                row["hot_pos"])):
                                        if row["is_horizontal"]:
                                            row["cold_pos"] += command.disy
                                            row["hot_pos"] += command.disy
                                        else:
                                            row["cold_pos"] += command.disx
                                            row["hot_pos"] += command.disx
                                    for rack in row["racks"]:
                                        if ("x_center" in row
                                                and None not in  (
                                                    rack["x_center"],
                                                    rack["y_center"])):
                                            rack["x_center"] += command.disx
                                            rack["y_center"] += command.disy
                                        for node in rack["sensors"]:
                                            if (None not in (node["x"],
                                                    node["y"])):
                                                node["x"] += command.disx
                                                node["y"] += command.disy
            rsp = f"{command.row} moved X:{command.disx},Y:{command.disy}"
            return command.response(rsp)
        return command.response("Genesis not found")

    def move_container(self, command):
        rsp_success = command.response(
                f"{command.container} moved X:{command.disx},Y:{command.disy}")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "containers" in room: # Only if old genesis
                                for container in room["containters"]:
                                    if container["name"] == command.container:
                                        container["x_center"] += command.disx
                                        container["y_center"] += command.disy
                                        return rsp_success
                                return command.response("Container not found")
                            return command.response("Deprecated genesis")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def move_rack(self, command):
        rsp_success = command.response(
                f"{command.rack} moved X:{command.disx},Y:{command.disy}")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                for rack in row["racks"]:
                                    if rack["name"] == command.rack:
                                        if ("x_center" in row
                                                and not None in (
                                                    rack["x_center"],
                                                    rack["y_center"])):
                                            rack["x_center"] += command.disx
                                            rack["y_center"] += command.disy
                                        for node in rack["sensors"]:
                                            if (not None in (node["x"],
                                                    node["y"])):
                                                node["x"] += command.disx
                                                node["y"] += command.disy
                                        return rsp_success
                                return command.response("Rack not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def move_gateway(self, command):
        rsp_success = command.response(
                f"{command.gateway} moved X:{command.disx},Y:{command.disy}")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "gateways" in room: # Only if old genesis
                                for gateway in room["gateways"]:
                                    if gateway["name"] == command.gateway:
                                        gateway["x"] += command.disx
                                        gateway["y"] += command.disy
                                        return rsp_success
                                return command.response("Gateway not found")
                            return command.response("Deprecated genesis")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def move_node(self, command):
        rsp_success = command.response(
                f"{command.node} moved X:{command.disx},Y:{command.disy}")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                for rack in row["racks"]:
                                    for node in rack["sensors"]:
                                        if node["name"] == command.node:
                                            node["x"] += command.disx
                                            node["y"] += command.disy
                                            return rsp_success
                                    return command.response("Node not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def add_room(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    room = {
                        "name": command.room,
                        "id": None,
                        "building": command.building,
                        "x_max": command.x_max,
                        "y_max": command.y_max,
                        "z_max": command.z_max,
                        "rows": [],
                        "gateways": [],
                        "containers": []
                    }
                    datacenter["rooms"].append(room)
                    return command.response(f"{command.room} added")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def add_row(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            row = {
                                "name": command.row,
                                "id": None,
                                "is_horizontal": command.is_horizontal,
                                "cold_pos": command.cold_pos,
                                "hot_pos": command.hot_pos,
                                "racks": []
                            }
                            room["rows"].append(row)
                            return command.response(f"{command.row} added")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def add_container(self, command):
        rsp_success = command.response(f"{command.container} added")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "containers" not in room:
                                room["containers"] = []
                            container = {
                                "name": command.container,
                                "id": None,
                                "x_min": command.x_min,
                                "y_min": command.y_min,
                                "x_max": command.x_max,
                                "y_max": command.y_max,
                            }
                            room["containers"].append(container)
                            return rsp_success
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def add_rack(self, command):
        rsp_success = command.response(f"{command.rack} added")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                if row["name"] == command.row:
                                    rack = {
                                        "name": command.rack,
                                        "id": None,
                                        "type": RACK_TYPE[command.type],
                                        "total_units": command.total_units,
                                        "x_center": command.x_center,
                                        "y_center": command.y_center,
                                        "x_size": command.x_size,
                                        "y_size": command.y_size,
                                        "sensors": []
                                    }
                                    row["racks"].append(rack)
                                    return rsp_success
                            return command.response("Row not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def add_gateway(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "gateways" not in room:
                                room["gateways"] = []
                            gateway = {
                                "name": command.gateway,
                                "id": None,
                                "device_id": command.device_id,
                                "mesh_id": command.mesh_id,
                                "x": command.x,
                                "y": command.y,
                                "z": command.z
                            }
                            room["gateways"].append(gateway)
                            return command.response(f"{command.gateway} added")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def add_node(self, command):
        rsp_success = command.response(f"{command.node} added")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                if row["name"] == command.row:
                                    for rack in row["racks"]:
                                        if rack["name"] == command.rack:
                                            source = NODE_SOURCE[command.source]
                                            node = {
                                                "name": command.node,
                                                "id": None,
                                                "mac_address": command.mac,
                                                "mesh_id": command.mesh_id,
                                                "mesh_uuid": command.uuid,
                                                "unit": command.unit,
                                                "source": source,
                                                "x": command.x,
                                                "y": command.y,
                                                "z": command.z
                                            }
                                            rack["sensors"].append(node)
                                            return rsp_success
                                    return command.response("Rack not found")
                            return command.response("Row not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_room(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for i in range(len(datacenter["rooms"])):
                        if datacenter["rooms"][i]["name"] == command.room:
                            del datacenter["rooms"][i]
                            return command.response(f"{command.room} deleted")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_row(self, command):
        rsp_success = command.response(f"{command.row} deleted")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for i in range(len(room["rows"])):
                                if room["rows"][i]["name"] == command.row:
                                    del room["rows"][i]
                                    return rsp_success
                            return command.response("Row not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_container(self, command):
        rsp_success = command.response(f"{command.container} deleted")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "containers" not in room:
                                room["containers"] = []
                            for i in range(len(room["containers"])):
                                if room["containers"][i]["name"] == \
                                        command.container:
                                    del room["containers"][i]
                                    return rsp_success
                            return command.response("Container not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_rack(self, command):
        rsp_success = command.response(f"{command.rack} deleted")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                if row["name"] == command.row:
                                    for i in range(len(row["racks"])):
                                        if row["racks"][i]["name"] == \
                                                command.rack:
                                            del row["racks"][i]
                                            return rsp_success
                                    return command.response("Rack not found")
                            return command.response("Row not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_gateway(self, command):
        rsp_success = command.response(f"{command.gateway} deleted")
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            if "gateways" not in room:
                                room["gateways"] = []
                            for i in range(len(room["gateways"])):
                                if room["gateways"][i]["name"] == \
                                        command.gateway:
                                    del room["gateways"][i]
                                    return rsp_success
                            return command.response("Gateway not found")
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_node(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    for room in datacenter["rooms"]:
                        if room["name"] == command.room:
                            for row in room["rows"]:
                                return self.del_node_2(command, row)
                    return command.response("Room not found")
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def del_node_2(self, command, row):
        rsp_success = command.response(f"{command.node} deleted")
        if row["name"] == command.row:
            for rack in row["racks"]:
                if rack["name"] == command.rack:
                    for i in range(len(rack["sensors"])):
                        if rack["sensors"][i]["name"] == command.node:
                            del rack["sensors"][i]
                            return rsp_success
                    return command.response("Node not found")
            return command.response("Rack not found")
        return command.response("Row not found")

    def import_room(self, command):
        if self.genesis is not None:
            for datacenter in self.genesis["datacenters"]:
                if datacenter["name"] == command.datacenter:
                    with open(command.room_file, 'r') as f:
                        room_data = json.load(f)
                    for i in range(len(datacenter["rooms"])):
                        if datacenter["rooms"][i]["name"] == room_data["name"]:
                            datacenter["rooms"][i] = room_data
                            return command.response("{} updated".format(
                                room_data["name"]))
                    datacenter["rooms"].append(room_data)
                    return command.response("{} imported".format(
                                room_data["name"]))
            return command.response("Datacenter not found")
        return command.response("Genesis not found")

    def import_genesis(self, command):
        with open(command.genesis_file, 'r') as f:
            self.genesis = json.load(f)
        return  command.response("Genesis successfully imported")
