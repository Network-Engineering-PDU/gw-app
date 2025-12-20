import inspect
import asyncio
import logging
import json
from datetime import datetime as dt

import ttgateway.commands as cmds
from ttgateway.config import config
from ttgateway.gateway.memory_database import MemoryDatabase
from ttgateway.virtual.virtual_node import VirtualNode
from ttgateway.virtual.virtual_node_db import VirtualNodeDatabase
from ttgateway.virtual.median_func import MedianFunction
from ttgateway.virtual.maximum_func import MaximumFunction
from ttgateway.virtual.minimum_func import MinimumFunction
from ttgateway.virtual.max_no_outliers_func import MaxNoOutliersFunction
from ttgateway.virtual.min_no_outliers_func import MinNoOutliersFunction
from ttgateway.virtual.weighted_sum_func import WeightedSumFunction
from ttgateway.virtual.backend_get_func import BackendGetFunction
from ttgateway.virtual.snmp_get_func import SnmpGetFunction
from ttgateway.virtual.modbus_get_func import ModbusGetFunction


logger = logging.getLogger(__name__)


class VirtualManager:
    VIRTUAL_SENSOR_PERIOD = 600

    def __init__(self, server):
        self.server = server
        self.functions = {
            MedianFunction.name(): MedianFunction,
            MaximumFunction.name(): MaximumFunction,
            MinimumFunction.name(): MinimumFunction,
            MaxNoOutliersFunction.name(): MaxNoOutliersFunction,
            MinNoOutliersFunction.name(): MinNoOutliersFunction,
            WeightedSumFunction.name(): WeightedSumFunction,
            BackendGetFunction.name(): BackendGetFunction,
            SnmpGetFunction.name(): SnmpGetFunction,
            ModbusGetFunction.name(): ModbusGetFunction,
        }
        database_file = f"{config.TT_DIR}/virtual_node_database.json"
        self.local_node_db = VirtualNodeDatabase(database_file, self)
        self.next_local_address = self.get_next_local_address()
        self.backend_node_db = MemoryDatabase()
        self.poll_task = None

    def get_next_local_address(self):
        max_address = VirtualNode.BASE_UNICAST_ADDRESS_LOCAL - 1
        for node in self.local_node_db.get_nodes():
            max_address = max(node.address, max_address)
        return max_address + 1

    def get_node(self, node_address: int) -> VirtualNode:
        for node in self.local_node_db.get_nodes():
            if node.address == node_address:
                return node
        for node in self.backend_node_db.get_nodes():
            if node.address == node_address:
                return node
        return None

    def create_local_node(self, function, args) -> VirtualNode:
        node = VirtualNode(self.next_local_address)
        self.add_function_to_node(node, function, args)
        self.next_local_address += 1
        self.local_node_db.store_node(node)
        node.function.start()
        return node

    def remove_local_node(self, node_address: int):
        for node in self.local_node_db.get_nodes():
            if node.address == node_address:
                self.local_node_db.remove_node(node)
                node.function.stop()
                return

    def stop_all(self):
        for node in self.local_node_db.get_nodes():
            node.function.stop()

        for node in self.backend_node_db.get_nodes():
            node.function.stop()

    def list_functions(self):
        function_list = []
        for function_name in self.functions:
            if function_name in self.functions:
                function_params = self._get_function_params(function_name)
                function = {
                    "name":   function_name,
                    "args": function_params
                }
                function_list.append(function)
        return function_list

    def _get_function_params(self, function_name):
        params = []
        func = self.functions[function_name]
        args = list(inspect.signature(func.__init__).parameters.values())
        for arg in args:
            arg_name = inspect.signature(func.__init__).parameters[arg.name]
            if str(arg_name) not in ("self", "node", "event_handler", "macs"):
                params.append(str(arg_name))
        return params

    def add_function_to_node(self, node, function_name, params):
        if function_name == "median":
            _type = params["type"]
            macs = params["sensor_list"]
            func = MedianFunction(self.server.event_handler, node, _type, macs,
                    self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name == "maximum":
            _type = params["type"]
            macs = params["sensor_list"]
            func = MaximumFunction(self.server.event_handler, node, _type, macs,
                    self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name == "minimum":
            _type = params["type"]
            macs = params["sensor_list"]
            func = MinimumFunction(self.server.event_handler, node, _type, macs,
                    self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name == "max_no_outliers":
            _type = params["type"]
            macs = params["sensor_list"]
            func = MaxNoOutliersFunction(self.server.event_handler, node, _type,
                    macs, self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name == "min_no_outliers":
            _type = params["type"]
            macs = params["sensor_list"]
            func = MinNoOutliersFunction(self.server.event_handler, node, _type,
                    macs, self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name in ("weighted_sum", "thermal_correlation_index"):
            _type = params["type"]
            weights = params["sensor_list"]
            func = WeightedSumFunction(self.server.event_handler, node, _type,
                    weights, self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name == "backend_get":
            _type = params["type"]
            url = params["url"]
            path = params["path"]
            func = BackendGetFunction(self.server.event_handler, node, _type,
                    url, path, self.VIRTUAL_SENSOR_PERIOD)
            node.function = func
        elif function_name == "snmp_get":
            if not self.server.snmp_client:
                raise ImportError("netsnmp is not installed")
            _type = params["type"]
            host = params["host"]
            community = params["community"]
            version = int(params["version"])
            oid = params["oid"]
            extra = params["extra_params"] if "extra_params" in params else None
            func = SnmpGetFunction(self.server.event_handler, node, _type,
                    host, community, version, oid, self.VIRTUAL_SENSOR_PERIOD,
                    self.server.snmp_client, extra_params=extra)
            node.function = func
        elif function_name == "modbus_get":
            if not self.server.modbus_client:
                raise ImportError("pymodbus is not installed")
            _type = params["type"]
            host = params["host"]
            port = int(params["port"])
            address = int(params["address"])
            slave = int(params["slave"])
            func = ModbusGetFunction(self.server.event_handler, node, _type,
                    host, port, address, slave, self.VIRTUAL_SENSOR_PERIOD,
                    self.server.modbus_client)
            node.function = func
        else:
            raise ValueError("Invalid function data")

    def node_from_json(self, _json):
        node_address = _json.get("address")
        mac = bytes.fromhex(_json.get("mac"))
        uuid = bytes.fromhex(_json.get("uuid"))
        name = _json.get("name")
        func = _json.get("function")
        node = VirtualNode(node_address, name, mac, uuid)
        try:
            self.add_function_to_node(node, func["name"], func)
            node.function.start()
            return node
        except (TypeError, AttributeError, ValueError):
            logger.warning(f"Invalid local virtual sensor {mac}")
            return None

    def start_polling(self):
        if self.poll_task is None:
            self.poll_task = asyncio.create_task(self.polling_backend_nodes())

    def stop_polling(self):
        if self.poll_task is not None:
            self.poll_task.cancel()
            self.poll_task = None

    async def polling_backend_nodes(self):
        try:
            backend = self.server.app_manager.interfaces["backend"]
            await asyncio.sleep(10)
            while True:
                if not backend.datacenter_id:
                    if not await backend.get_datacenter_id():
                        logger.debug("Unable to get datacenter_id")
                        await asyncio.sleep(30)
                        continue
                url = f"{backend.url}{backend.slug}/core/datacenters/" + \
                    f"{backend.datacenter_id}/virtual-sensors"
                rsp = await backend.http.request("virtual_polling", "GET", url)
                invalid_nodes = []
                if rsp is not None and rsp.ok:
                    nodes = rsp.json()["results"]
                    pages = rsp.json()["pagination"]["num_pages"]
                    if pages > 1:
                        for page in range(pages - 1):
                            rsp = await backend.http.request("virtual_polling",
                                "GET", url, params={"page": page + 2})
                            nodes += rsp.json()["results"]
                    for node in nodes:
                        current_node = self.get_node(node["unicast_address"])
                        updated_dt = dt.fromisoformat(node["updated_at"][:-1])
                        updated_ts = updated_dt.timestamp()
                        if (current_node is None
                                or updated_ts > current_node.updated_ts):
                            try:
                                mesh_uuid = None
                                if node["mesh_uuid"]:
                                    mesh_uuid = bytes.fromhex(node["mesh_uuid"])
                                new_node = VirtualNode(node["unicast_address"],
                                    node["name"],
                                    bytes.fromhex(node["mac_address"]),
                                    mesh_uuid)
                                new_node.updated_ts = updated_ts
                                self.add_function_to_node(new_node,
                                        node["function_name"], node["args"])
                                new_node.function.start()
                                self.backend_node_db.store_node(new_node)
                                logger.debug("Add backend virtual sensor " + \
                                        f"{node['mac_address']}")
                            except (TypeError, AttributeError, ValueError):
                                invalid_nodes.append(node["mac_address"])
                                continue
                if len(invalid_nodes) > 0:
                    logger.log(9, f"Invalid nodes: {invalid_nodes}")
                    w_msg = f"{len(invalid_nodes)} invalid virtual sensors"
                    logger.warning(w_msg)
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(e)
            raise

    async def dispatch(self, command) -> cmds.Response:
        if isinstance(command, cmds.VirtualListNodes):
            local_nodes = self.local_node_db.get_nodes()
            backend_nodes = self.backend_node_db.get_nodes()
            virtual_nodes = local_nodes + backend_nodes
            nodes_json = [node.to_json() for node in virtual_nodes]
            return command.response(extra_data={"node_list": nodes_json})

        if isinstance(command, cmds.VirtualCreateNode):
            try:
                node = self.create_local_node(command.function,
                        json.loads(command.args))
            except (TypeError, ValueError):
                logger.exception("Error creating virtual node")
                return command.response("Invalid params", False)
            return command.response(extra_data={"node": node.to_json()})

        if isinstance(command, cmds.VirtualRemoveNode):
            node = self.get_node(command.node_address)
            if node is None:
                return  command.response("Unknown virtual node", False)
            if not node.is_local():
                return command.response("Node is not local", False)
            self.remove_local_node(node.address)
            return command.response()

        if isinstance(command, cmds.VirtualListFunctions):
            return command.response(extra_data={"function_list":
                self.list_functions()})
