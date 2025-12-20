import json
import struct
from typing import List, Dict, Union
import os


class CommandId:
    Response = 0x0000

    GatewayInit = 0x0001 # Deprecated
    GatewayStartScan = 0x0002
    GatewayStopScan = 0x0003
    GatewayStatus = 0x0004
    GatewayConfigured = 0x0005 # Deprecated
    GatewayGetSleep = 0x0006
    GatewaySetSleep = 0x0007
    GatewayCheck = 0x0008
    GatewayConfigMesh = 0x0009
    GatewayStartRemote = 0x000A # Deprecated
    GatewayRestart = 0x000B # Deprecated
    GatewayListener = 0x000C

    NodeList = 0x0101
    NodeCancelTasks = 0x0102
    NodeReset = 0x0103
    NodeRate = 0x0104
    NodeRssiStart = 0x0105
    NodeRssiGet = 0x0106
    NodeAccelOff = 0x0107
    NodeOta = 0x0108
    NodeTaskCreate = 0x0109
    NodeOtaStatus = 0x010A
    NodeBeaconStart = 0x010B
    NodeBeaconStop = 0x010C
    NodeTaskDelete = 0x010D
    NodeTaskModify = 0x010E
    NodeSetPwmtConfig = 0x010F
    NodeSetPwmtConv = 0x0110
    NodeTempMode = 0x0111
    NodeCalibrate = 0x0112
    NodeResetCalibration = 0x0113
    NodeSetDAC = 0x0114
    NodeSetRelay = 0x0115
    NodeRssiPing = 0x0116
    NodeTasksGet = 0x0117
    NodeReboot = 0x0118
    NodeSummary = 0x0119
    NodeSetFailsafe = 0x011A
    NodeSendOutVector = 0x011B
    NodeOutputStatus = 0x011C

    VirtualListNodes = 0x0201
    VirtualCreateNode = 0x0202
    VirtualRemoveNode = 0x0203
    VirtualListFunctions = 0x0204

    AppListInterfaces = 0x0401
    AppEnableInterface = 0x0402
    AppDisableInterface = 0x0403
    AppSaveState = 0x0404

    FaultStatus = 0x0501
    FaultEnable = 0x0502
    FaultDisable = 0x0503
    FaultListNodes = 0x0504
    FaultNewCluster = 0x0505
    FaultGetCluster = 0x0506
    FaultTest = 0x05FF

    SnmpGet = 0x0601
    SnmpWalk = 0x0602

    ModbusReadCoils = 0x0701
    ModbusReadDiscreteInputs = 0x0702
    ModbusReadHoldingRegisters = 0x0703
    ModbusReadInputRegisters = 0x0704

    SetLogLevelCommand = 0x0A01
    StartRemoteClient = 0x0A02
    StopRemoteClient = 0x0A03
    GetElementInfo = 0x0A04
    ShowLog = 0x0A05
    StartHttpLogging = 0x0A06
    StopHttpLogging = 0x0A07
    ConfigSet = 0x0AF1
    ConfigGet = 0x0AF2
    ConfigSave = 0x0AF3
    ConfigBackup = 0x0AF4
    ConfigErase = 0x0AF5
    ShellRemote = 0x0AF6

    LocationGetGenesis = 0x0B01
    LocationPostGenesis = 0x0B02
    LocationSaveGenesis = 0x0B03
    LocationListDatacenters = 0x0B04
    LocationListRooms = 0x0B05
    LocationListRows = 0x0B06
    LocationListContainers = 0x0B07
    LocationListRacks = 0x0B08
    LocationListGateways = 0x0B09
    LocationListNodes = 0x0B0A
    LocationMoveGlobal = 0x0B0B
    LocationMoveRow = 0x0B0C
    LocationMoveContainer = 0x0B0D
    LocationMoveRack = 0x0B0E
    LocationMoveGateway = 0x0B0F
    LocationMoveNode = 0x0B10
    LocationAddRoom = 0x0B11
    LocationAddRow = 0x0B12
    LocationAddContainer = 0x0B13
    LocationAddRack = 0x0B14
    LocationAddGateway = 0x0B15
    LocationAddNode = 0x0B16
    LocationImportRoom = 0x0B17
    LocationDelRoom = 0x0B18
    LocationDelRow = 0x0B19
    LocationDelContainer = 0x0B1A
    LocationDelRack = 0x0B1B
    LocationDelGateway = 0x0B1C
    LocationDelNode = 0x0B1D
    LocationImportGenesis = 0x0B1E

    SimulatorStart = 0x0C01
    SimulatorStop = 0x0C02
    SimulatorStatus = 0x0C03

    BackendGetNodes = 0x0D01

    GatewayMngrInit = 0x0E01
    GatewayMngrList = 0x0E02
    GatewayMngrCheckPT = 0x0E03
    GatewayMngrUninit = 0x0E04

    ThreadList = 0x0F01


class SerialMessage:
    def __init__(self):
        self.command_id = getattr(CommandId, self.__class__.__name__)

    def to_json(self):
        raise NotImplementedError

    def serialize(self) -> bytes:
        """ Transforms a command to a byte array, withs its length in
        the first three bytes, using pickle.

        :return: Command as bytes.
        :rtype: bytes
        """
        json_bytes = json.dumps(self.to_json()).encode()
        data_bytes = bytearray()
        data_bytes += struct.pack("<I", len(json_bytes))
        data_bytes += json_bytes
        return data_bytes

    @classmethod
    def deserialize(cls, json_bytes: bytes) -> "SerialCommand":
        json_data = json.loads(json_bytes.decode())
        params = json_data.get("params", {})
        for attr_name in dir(CommandId):
            attr = getattr(CommandId, attr_name)
            if isinstance(attr, int) and attr == json_data["command_id"]:
                return globals()[attr_name](**params)
        return None


class Response(SerialMessage):
    """ Command response. This class is used to respond to any command,
    and it should be sent back to the client.

    :param original_command: The command id of the receiced command, to
        which this is the response.
    :type original_command: int
    :param info: Quick message response. Optional.
    :type info: str
    :param success: Wheter the command was completed successfully.
    :type success: bool
    :param data: Custom command response data. See each command for
        more information. Optional.
    :type data: Dict
    """
    def __init__(self, original_command: int, info: str="", success: bool=True,
            extra_data: Dict=None):
        self.original_command = original_command
        self.info = info
        self.success = success
        if extra_data is None:
            extra_data = {}
        self.extra_data = extra_data
        super().__init__()

    def to_json(self) -> str:
        json_data = {
            "command_id": self.command_id,
            "original_command": self.original_command,
            "success": self.success,
        }
        if self.info:
            json_data["info"] = self.info
        if self.extra_data:
            json_data["data"] = self.extra_data
        return json_data


class Command(SerialMessage):
    """ Base command, should be inherit by any other command. """
    def __init__(self, params: Dict):
        self.__params = params
        super().__init__()

    def __getattr__(self, name: str):
        if name in self.__params:
            return self.__params[name]
        raise AttributeError

    def response(self, info: str="", success: bool=True, extra_data: Dict=None):
        if extra_data is None:
            extra_data = {}
        return Response(self.command_id, info, success, extra_data)

    def to_json(self) -> str:
        return {
            "command_id": self.command_id,
            "params": self.__params,
        }


class GatewayCommand(Command):
    """ Base gateway command. Should not be instantiated. """


class GatewayCheck(GatewayCommand):
    """ Checks the uart connection with the microcontroller.

    :param gw_id: Gateway ID.
    :type gw_id: str
    """
    def __init__(self, gw_id: str=""):
        params = {
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayStartScan(GatewayCommand):
    """ Starts scanning of new nodes, to provision and add them to the
    mesh network.

    :param timeout: Time to automatically stop the scanning, in
        seconds. Set to 0 to scan indefinitely.
    :type timeout: int
    :param one: Provision only one node.
    :type one: bool
    :param gw_id: Gateway ID.
    :type gw_id: str
    """
    def __init__(self, timeout: int=0, one: bool=False, gw_id: str=""):
        params = {
            "timeout": timeout,
            "one": one,
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayStopScan(GatewayCommand):
    """ Manually stops scanning, if timeout=0 whas given when the
    scanning begun.

    :param gw_id: Gateway ID.
    :type gw_id: str
    """
    def __init__(self, gw_id: str=""):
        params = {
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayStatus(GatewayCommand):
    """ Shows some status parameters.

    :param gw_id: Gateway ID.
    :type gw_id: str

    Response extra data:
        version: str
        scanning: bool
        provisioning: bool
        nodes: int
        max_nodes: int
        unicast_addr: int
    """
    def __init__(self, gw_id: str=""):
        params = {
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayGetSleep(GatewayCommand):
    """ Gets the long wake up period.

    Response extra data:
        sleep_time: int
    """
    def __init__(self, gw_id: str=""):
        params = {
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewaySetSleep(GatewayCommand):
    """ Sets the long wake up period.

    Response extra data:
        old_sleep_time: int
        new_sleep_time: int

    :param time: Period to set, in seconds.
    :type time: int
    :param gw_id: Gateway ID.
    :type gw_id: str
    """
    def __init__(self, time: int=43200, gw_id: str=""):
        params = {
            "time": time,
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayConfigMesh(GatewayCommand):
    """ Configures gateway Mesh net key and unicast address

    :param netkey: Mesh net key
    :type netkey: bytes[16]
    :param unicast_address: Mesh unicast address
    :type unicast_address: int
    :param gw_id: Gateway ID.
    :type gw_id: str
    """
    def __init__(self, netkey: str="", unicast_address: int=0, gw_id: str=""):
        params = {
            "netkey": netkey,
            "unicast_address": unicast_address,
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayListener(GatewayCommand):
    """ Enables/disables listener mode.

    :param value: True enables, False disables the listener mode.
    :type value: bool
    :param gw_id: Gateway ID.
    :type gw_id: str
    """
    def __init__(self, value: bool, gw_id: str=""):
        params = {
            "value": value,
            "gw_id": gw_id
        }
        super().__init__(params)


class GatewayMngrCommand(Command):
    """ Base gateway manager command. Should not be instantiated. """


class GatewayMngrInit(GatewayMngrCommand):
    """ Initializes the gateway manager.
    """
    def __init__(self):
        super().__init__({})


class GatewayMngrUninit(GatewayMngrCommand):
    """ Stops the gateway manager.
    """
    def __init__(self):
        super().__init__({})


class GatewayMngrList(GatewayMngrCommand):
    """ List gateways managed by the gateway manager.
    """
    def __init__(self):
        super().__init__({})


class GatewayMngrCheckPT(GatewayMngrCommand):
    """ Checks passthrough connection.
    """
    def __init__(self):
        super().__init__({})


class NodeList(GatewayMngrCommand):
    """ Gets a list of all the nodes.

    Response extra data:
        node_list: List[Dict]
            mac: str
            addr: int
            uuid: str
            tasks: List[str]
            sleep_period: int
            last_wake_ts: int
            last_msg_ts: int
    """
    def __init__(self, tel: bool=False, co2: bool=False, iaq: bool=False,
            bat: bool=False, ota: bool=False, pwmt:bool=False, tab: bool=False,
            nodes: List[str]=None, last: int=None, stats: bool=False,
            tasks: bool=False, cvg: bool=False):
        params = {
            "tel": tel,
            "co2": co2,
            "iaq": iaq,
            "bat": bat,
            "ota": ota,
            "pwmt": pwmt,
            "tab": tab,
            "nodes": nodes,
            "last": last,
            "stats": stats,
            "tasks": tasks,
            "cvg": cvg,
        }
        super().__init__(params)


class NodeSummary(GatewayMngrCommand):
    """ Get a summary of the nodes.
    """
    def __init__(self):
        super().__init__({})


class NodeCancelTasks(GatewayMngrCommand):
    """ Cancel all current tasks for the given nodes.

    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeReset(GatewayMngrCommand):
    """ Resets the given nodes.

    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeRate(GatewayMngrCommand):
    """ Changes the rate period for the given nodes.

    :param rate: New rate to set.
    :type rate: int
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, rate: int=600, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes,
            "rate": rate
        }
        super().__init__(params)


class NodeRssiStart(GatewayMngrCommand):
    """ Schedules rssi sending between nodes.

    :param datetime: Date and time to be scheduled ("dd/mm/yyyy HH:MM:SS")
    :type datetime: str
    """
    def __init__(self, datetime: str=""):
        params = {
            "datetime": datetime
        }
        super().__init__(params)


class NodeRssiGet(GatewayMngrCommand):
    """ Gets a list of rssi values stored by a node of other nodes.

    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeRssiPing(GatewayMngrCommand):
    """ Sends a ping packet to the given node/s.

    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeAccelOff(GatewayMngrCommand):
    """ Changes the rate period for the given nodes.
    """
    def __init__(self):
        super().__init__({})


class NodeOta(GatewayMngrCommand):
    """ Schedules a ota update.

    :param ota_zip: Zip file with OTA information and firmware.
    :type ota_zip: str
    :param datetime: Date and time to be scheduled ("dd/mm/yyyy HH:MM:SS").
    :type datetime: str
    :param nodes: List with the macs of the nodes. If emtpy the update is still
                  sent at the scheduled time.
    :type nodes: List[str]
    """
    def __init__(self, ota_zip, datetime: str="", ota_type: str="",
            nodes: List[str]=None):
        ota_zip_path = os.path.abspath(ota_zip)
        if nodes is None:
            nodes = []
        params = {
            "ota_zip": ota_zip_path,
            "datetime": datetime,
            "ota_type": ota_type,
            "nodes": nodes
        }
        super().__init__(params)


class NodeTaskCreate(GatewayMngrCommand):
    """ Schedules a raw task.
    :param opcode: Existing opcode for the new task.
    :type opcode: int
    :param datetime: Date and time to be scheduled ("dd/mm/yyyy HH:MM:SS").
    :type datetime: str
    :param period: Period in seconds of the task to be scheduled.
    :type datetime: int
    :param nodes: List with the macs of the nodes. If emtpy the task will be
                  sent to all nodes at the scheduled time.
    :type nodes: List[str]
    """
    def __init__(self, opcode: int=0, datetime: str="", period: int=0,
            clock: int=1, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "opcode": opcode,
            "datetime": datetime,
            "period": period,
            "clock": clock,
            "nodes": nodes
        }
        super().__init__(params)


class NodeTaskDelete(GatewayMngrCommand):
    """ Delete a node task by opcode.
    :param opcode: Existing opcode for the new task.
    :type opcode: int
    :param nodes: List with the macs of the nodes. If emtpy the task will be
                  sent to all nodes at the scheduled time.
    :type nodes: List[str]
    """
    def __init__(self, opcode: int=0, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "opcode": opcode,
            "nodes": nodes
        }
        super().__init__(params)


class NodeTasksGet(GatewayMngrCommand):
    """ Get scheduled node tasks.
    :param nodes: List with the macs of the nodes. If emtpy the task will be
                  sent to all nodes at the scheduled time.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeTaskModify(GatewayMngrCommand):
    """ Modifies an existing task.
    :param opcode: Existing opcode for the new task.
    :type opcode: int
    :param datetime: Date and time to be scheduled ("dd/mm/yyyy HH:MM:SS").
    :type datetime: str
    :param period: Period in seconds of the task to be scheduled.
    :type datetime: int
    :param nodes: List with the macs of the nodes. If emtpy the task will be
                  sent to all nodes at the scheduled time.
    :type nodes: List[str]
    """
    def __init__(self, opcode: int=0, datetime: str="", period: int=0,
            clock: int=1, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "opcode": opcode,
            "datetime": datetime,
            "period": period,
            "clock": clock,
            "nodes": nodes
        }
        super().__init__(params)


class NodeOtaStatus(GatewayMngrCommand):
    """ Get OTA status.
    :param nodes: List with the macs of the nodes. If emtpy the OTA status will
                  be sent to all nodes at the scheduled time.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeBeaconStart(GatewayMngrCommand):
    """ Start node BLE beacon.

    :param period_ms: Time between beacon packets, in milliseconds.
    :type period_ms: int
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, period_ms: int, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "period_ms": period_ms,
            "nodes": nodes
        }
        super().__init__(params)


class NodeBeaconStop(GatewayMngrCommand):
    """ Stop node BLE beacon.

    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes
        }
        super().__init__(params)


class NodeSetPwmtConfig(GatewayMngrCommand):
    """ Set power meter voltage, current and energy thresholds.
    :param phases: Phases to receive (TOT|L1|L2|L3).
    :type phases: int
    :param stats: Stats to receive (avg|max|min).
    :type stats: int
    :param values_ph: Phase values to receive (VIF|Ppf|QSph|E).
    :type values_ph: int
    :param values_tot: Total values to receive (PQS|phph|vph|E).
    :type values_tot: int
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, phases: int, stats: int, values_ph: int, values_tot: int,
            nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "phases": phases,
            "stats": stats,
            "values_ph": values_ph,
            "values_tot": values_tot,
            "nodes": nodes
        }
        super().__init__(params)


class NodeSetPwmtConv(GatewayMngrCommand):
    """ Set the pwmt channels conversion factor of the given node.
    :param kv: New votage conversion factor.
    :type kv: int
    :param ki: New current conversion factor.
    :type ki: int
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, kv: int, ki: int, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "kv": int(kv),
            "ki": int(ki),
            "nodes": nodes
        }
        super().__init__(params)


class NodeTempMode(GatewayMngrCommand):
    """ Get power meter alerts for the given node(s).
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, mode: int, nodes: List[str]=None):
        if nodes is None:
            nodes = []
        params = {
            "nodes": nodes,
            "mode": mode,
        }
        super().__init__(params)


class NodeCalibrate(GatewayMngrCommand):
    """ Calibrate the sensors of the given node(s).
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, temp_offset: int, humd_offset: int, press_offset: int,
            node: str=""):
        params = {
            "node": node,
            "temp_offset": temp_offset,
            "humd_offset": humd_offset,
            "press_offset": press_offset
        }
        super().__init__(params)


class NodeResetCalibration(GatewayMngrCommand):
    """ Reset the calibration of the sensor for the given node(s).
    :param nodes: List with the macs of the nodes.
    :type nodes: List[str]
    """
    def __init__(self, temp: bool, humd: bool, press: bool,
            node: str=""):
        params = {
            "node": node,
            "temp": temp,
            "humd": humd,
            "press": press
        }
        super().__init__(params)


class NodeSetDAC(GatewayMngrCommand):
    """ Sets the DAC output of the given node.
    :param nodes: Mac of the node.
    :type nodes: str
    :param value: Value of the DAC output. 10-bit DAC (0-1023)
    :type value: integer
    """
    def __init__(self, value: int, node: str=""):
        params = {
            "node": node,
            "value": value,
        }
        super().__init__(params)


class NodeSetRelay(GatewayCommand):
    """ Sets the relay output of the given node.
    :param nodes: MAC of the node.
    :type nodes: str
    :param status: Status of the relay output.
    :type status: integer
    """
    def __init__(self, status: int, node: str=""):
        params = {
            "node": node,
            "status": status,
        }
        super().__init__(params)


class NodeSetFailsafe(GatewayCommand):
    """ Sets the failsafe of the given node.
    :param nodes: MAC of the node.
    :type nodes: str
    :param relay: Status of the relay. 0 (clear), 1 (set)
    :type relay: integer
    :param dac: Value of the DAC.
    :type dac: float
    """
    def __init__(self, relay: int, dac: float, node: str=""):
        params = {
            "node": node,
            "relay": relay,
            "dac": dac,
        }
        super().__init__(params)


class NodeSendOutVector(GatewayCommand):
    """ Send output vector to the given node.
    :param path: Path to the cmd vector JSON file.
    :type path: str
    """
    def __init__(self, path: str=""):
        params = {
            "path": path,
        }
        super().__init__(params)


class NodeOutputStatus(GatewayCommand):
    """ Get output status list.
    """
    def __init__(self):
        super().__init__({})


class NodeReboot(GatewayMngrCommand):
    def __init__(self, node: str=""):
        params = {
            "node": node,
        }
        super().__init__(params)


class VirtualCommand(Command):
    """ Base virtual command. Should not be instantiated. """


class VirtualListNodes(VirtualCommand):
    """ List virtual nodes.

    Response extra data:
        node_list: List[Dict]
            name: str
            address: int
            mac: str
            uuid: str
            running: bool
            functions: List[dict]
                name: str
                params: List
                macs: List[str]
    """
    def __init__(self):
        super().__init__({})


class VirtualCreateNode(VirtualCommand):
    """ Create a virtual node.

    Response extra data:
        node: Dict
            name: str
            address: int
            mac: str
            uuid: str
            running: bool
            functions: List[dict]
                name: str
                params: List
                macs: List[str]
    """
    def __init__(self, function, args):
        params = {
            "function": function,
            "args": args
        }
        super().__init__(params)


class VirtualRemoveNode(VirtualCommand):
    """ Remove virtual node.

    :param node_address: Virtual node address.
    :type nodes: int
    """
    def __init__(self, node_address: int):
        params = {
            "node_address": node_address
        }
        super().__init__(params)


class VirtualListFunctions(VirtualCommand):
    """ List virtual functions.

    Response extra data:
        function_list: List[str]
    """
    def __init__(self):
        super().__init__({})


class AppCommand(Command):
    """ Base app command. Should not be instantiated. """


class AppListInterfaces(AppCommand):
    """ Return the available interfaces and their status.
        Response extra data:
            interfaces: Dict[str, bool]
    """
    def __init__(self):
        super().__init__({})


class AppEnableInterface(AppCommand):
    """ Enable interface.

    :param interface: Interface name.
    :type interface: str
    """
    def __init__(self, interface: str=""):
        params = {
            "interface": interface,
        }
        super().__init__(params)


class AppDisableInterface(AppCommand):
    """ Disable interface.

    :param interface: Interface name.
    :type interface: str
    """
    def __init__(self, interface: str=""):
        params = {
            "interface": interface,
        }
        super().__init__(params)


class AppSaveState(AppCommand):
    """ Save current state. This command intended to be use before
    rebooting, so the apps don't lose the current information for after
    the reboot.
    """
    def __init__(self):
        super().__init__({})


class FaultCommand(Command):
    """ Base fault command. Should not be instantiated. """


class FaultStatus(FaultCommand):
    """ Return the fault tolerance module status, including the
    startegy and the transport being used.

    Response extra data:
        status: bool
        strategy: str
        transport: str
    """
    def __init__(self):
        super().__init__({})


class FaultEnable(FaultCommand):
    """ Enable fault tolerance module using a given transport. """
    def __init__(self):
        super().__init__({})


class FaultDisable(FaultCommand):
    """ Disable fault tolerance module. """
    def __init__(self):
        super().__init__({})


class FaultListNodes(FaultCommand):
    """ List Raft nodes.

    Response extra data:
        node_list: List
    """
    def __init__(self):
        super().__init__({})


class FaultNewCluster(FaultCommand):
    """ Update Raft cluster.

    :param cluster: New cluster.
    :type cluster: list
    """
    def __init__(self, cluster):
        params = {
            "cluster": cluster
        }
        super().__init__(params)


class FaultGetCluster(FaultCommand):
    """ Download cluster from backend."""
    def __init__(self):
        super().__init__({})


class FaultTest(FaultCommand):
    def __init__(self, cmd: dict):
        params = {
            "cmd": cmd
        }
        super().__init__(params)


class SnmpCommand(Command):
    """ Base SNMP client command. """


class SnmpGet(SnmpCommand):
    """ SNMP GET requests.
    :param host: Agent IP address.
    :type host: str
    :param community: Community string.
    :type community: str
    :param oid: Object identifier.
    :type oid: str
    :param version: SNMP version (1 or 2).
    :type version: int

    Response extra data:
        response: Tuple[type: str, value: str|int|None]
    """
    def __init__(self, host: str, community: str, oid: str, version: int):
        params = {
            "host": host,
            "community": community,
            "oid": oid,
            "version": version,
        }
        super().__init__(params)


class SnmpWalk(SnmpCommand):
    """ SNMP GET requests.
    :param host: Agent IP address.
    :type host: str
    :param community: Community string.
    :type community: str
    :param oid: Object identifier.
    :type oid: str
    :param version: SNMP version (1 or 2).
    :type version: int

    Response extra data:
        response: List[Tuple[oid: str, type: str, value: str|int|None]]
    """
    def __init__(self, host: str, community: str, oid: str, version: int):
        params = {
            "host": host,
            "community": community,
            "oid": oid,
            "version": version,
        }
        super().__init__(params)


class ModbusCommand(Command):
    """ Base Modbus client command. """


class ModbusReadCoils(ModbusCommand):
    """ Modbus read coils requests.
    :param host: IP address.
    :type host: str
    :param port: Modbus port number.
    :type host: int
    :param address: Start address to read from.
    :type address: int
    :param slave: Modbus slave ID.
    :type slave: int

    Response extra data:
        response: Tuple[type: str, value: str|int|None]
    """
    def __init__(self, host: str, port: int, address: int,
            slave: int):
        params = {
            "host": host,
            "port": port,
            "address": address,
            "slave": slave,
        }
        super().__init__(params)


class ModbusReadDiscreteInputs(ModbusCommand):
    """ Modbus read discrete input requests.
    :param host: IP address.
    :type host: str
    :param port: Modbus port number.
    :type host: int
    :param address: Start address to read from.
    :type address: int
    :param slave: Modbus slave ID.
    :type slave: int


    Response extra data:
        response: Tuple[type: str, value: str|int|None]
    """
    def __init__(self, host: str, port: int, address: int, slave: int):
        params = {
            "host": host,
            "port": port,
            "address": address,
            "slave": slave,
        }
        super().__init__(params)


class ModbusReadHoldingRegisters(ModbusCommand):
    """ Modbus read holding registers requests.
    :param host: IP address.
    :type host: str
    :param port: Modbus port number.
    :type host: int
    :param address: Start address to read from.
    :type address: int
    :param slave: Modbus slave ID.
    :type slave: int


    Response extra data:
        response: Tuple[type: str, value: str|int|None]
    """
    def __init__(self, host: str, port: int, address: int, slave: int):
        params = {
            "host": host,
            "port": port,
            "address": address,
            "slave": slave,
        }
        super().__init__(params)


class ModbusReadInputRegisters(ModbusCommand):
    """ Modbus read input registers requests.
    :param host: IP address.
    :type host: str
    :param port: Modbus port number.
    :type host: int
    :param address: Start address to read from.
    :type address: int
    :param slave: Modbus slave ID.
    :type slave: int

    Response extra data:
        response: Tuple[type: str, value: str|int|None]
    """
    def __init__(self, host: str, port: int, address: int, slave: int):
        params = {
            "host": host,
            "port": port,
            "address": address,
            "slave": slave,
        }
        super().__init__(params)


class SetLogLevelCommand(Command):
    """ Set global log level. """
    def __init__(self, log_level: int, logger: str=None):
        params = {
            "log_level": log_level,
            "logger": logger
        }
        super().__init__(params)


class StartRemoteClient(Command):
    """ Start websocket client. """
    def __init__(self):
        super().__init__({})


class StopRemoteClient(Command):
    """ Stop websocket client. """
    def __init__(self):
        super().__init__({})


class GetElementInfo(Command):
    """ Get debug info from element.

    :param element: Object route to element, from class Server.
    :type element: str

    Response extra data:
        type: str
        value: str
    """
    def __init__(self, element: str):
        params = {
            "element": element
        }
        super().__init__(params)


class ShowLog(Command):
    """ Show the TycheTools gateway log.

    :param lines: Number of lines to output, instead of the last 10.
    :type lines: int
    :param grep: String PATTERNS to search for in log file.
    :type grep: str
    :param datetime: UTC datetime of log file: \"dd/mm/yyyy HH:MM:SS\".
    :type datetime: str
    """
    def __init__(self, lines: int=10, grep: str="", datetime: str=""):
        params = {
            "lines": lines,
            "grep": grep,
            "datetime": datetime
        }
        super().__init__(params)


class ShellRemote(Command):
    """ Execute a gateway command as if at the OS prompt.

    :param command: The command to run including the arguments to pass
    :type command: str
    """
    def __init__(self, command: str=""):
        params = {
            "command": command
        }
        super().__init__(params)


class StartHttpLogging(Command):
    """ Start HTTP logging """
    def __init__(self):
        super().__init__({})


class StopHttpLogging(Command):
    """ Stop HTTP logging """
    def __init__(self):
        super().__init__({})


class ConfigCommand(Command):
    """ Base config command. Should not be instantiated. """


class ConfigSet(ConfigCommand):
    """ Set configuration value.

    :param module: Configuration module name.
    :type module: str
    :param field: Configuration field (key).
    :type field: str
    :param value: New value to set.
    :type value: int|str
    """
    def __init__(self, module: str, field: str, value: Union[int, str]):
        params = {
            "module": module,
            "field": field,
            "value": value
        }
        super().__init__(params)


class ConfigGet(ConfigCommand):
    """ Get configuration value.

    :param module: Configuration module name.
    :type module: str
    :param field: Configuration field (key).
    :type field: str

    Response extra data:
        value: int|str
    """
    def __init__(self, module: str, field: str):
        params = {
            "module": module,
            "field": field,
        }
        super().__init__(params)


class ConfigSave(ConfigCommand):
    """ Save configuration in config file. """
    def __init__(self):
        super().__init__({})


class ConfigBackup(ConfigCommand):
    """ Create a backup of the mesh database and config file. """
    def __init__(self):
        super().__init__({})


class ConfigErase(ConfigCommand):
    """ Erase mesh database and config file. """
    def __init__(self):
        super().__init__({})


class LocationCommand(Command):
    """ Base location command. Should not be instantiated. """


class LocationGetGenesis(LocationCommand):
    def __init__(self):
        super().__init__({})


class LocationPostGenesis(LocationCommand):
    def __init__(self):
        super().__init__({})


class LocationSaveGenesis(LocationCommand):
    def __init__(self):
        super().__init__({})


class LocationListDatacenters(LocationCommand):
    def __init__(self):
        super().__init__({})


class LocationListRooms(LocationCommand):
    def __init__(self, datacenter: str):
        params = {
            "datacenter": datacenter
        }
        super().__init__(params)


class LocationListRows(LocationCommand):
    def __init__(self, datacenter: str, room: str):
        params = {
            "datacenter": datacenter,
            "room": room
        }
        super().__init__(params)


class LocationListContainers(LocationCommand):
    def __init__(self, datacenter: str, room: str):
        params = {
            "datacenter": datacenter,
            "room": room
        }
        super().__init__(params)


class LocationListRacks(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str=""):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row
        }
        super().__init__(params)


class LocationListGateways(LocationCommand):
    def __init__(self, datacenter: str, room: str):
        params = {
            "datacenter": datacenter,
            "room": room
        }
        super().__init__(params)


class LocationListNodes(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str="", rack: str=""):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "rack": rack
        }
        super().__init__(params)


class LocationMoveGlobal(LocationCommand):
    def __init__(self, datacenter: str, room: str, disx: float, disy: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "disx": disx,
            "disy": disy
        }
        super().__init__(params)


class LocationMoveRow(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str,  disx: float,
            disy: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "disx": disx,
            "disy": disy
        }
        super().__init__(params)


class LocationMoveContainer(LocationCommand):
    def __init__(self, datacenter: str, room: str, container: str,  disx: float,
            disy: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "container": container,
            "disx": disx,
            "disy": disy
        }
        super().__init__(params)


class LocationMoveRack(LocationCommand):
    def __init__(self, datacenter: str, room: str, rack: str,  disx: float,
            disy: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "rack": rack,
            "disx": disx,
            "disy": disy
        }
        super().__init__(params)


class LocationMoveGateway(LocationCommand):
    def __init__(self, datacenter: str, room: str, gateway: str,  disx: float,
            disy: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "gateway": gateway,
            "disx": disx,
            "disy": disy
        }
        super().__init__(params)


class LocationMoveNode(LocationCommand):
    def __init__(self, datacenter: str, room: str, node: str,  disx: float,
            disy: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "node": node,
            "disx": disx,
            "disy": disy
        }
        super().__init__(params)


class LocationAddRoom(LocationCommand):
    def __init__(self, datacenter: str, room: str, building: str, x_max: float,
            y_max: float, z_max: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "building": building,
            "x_max": x_max,
            "y_max": y_max,
            "z_max": z_max
        }
        super().__init__(params)


class LocationAddRow(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str,
            is_horizontal: bool, hot_pos: float, cold_pos: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "is_horizontal": is_horizontal,
            "hot_pos": hot_pos,
            "cold_pos":cold_pos
        }
        super().__init__(params)


class LocationAddContainer(LocationCommand):
    def __init__(self, datacenter: str, room: str, container: str,
            x_min: float, y_min: float, x_max: float, y_max: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "container": container,
            "x_min": x_min,
            "y_min": y_min,
            "x_max": x_max,
            "y_max": y_max
        }
        super().__init__(params)


class LocationAddRack(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str, rack: str,
            _type: str, total_units: int, x_center: float, y_center: float,
            x_size: float, y_size: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "rack": rack,
            "type": _type,
            "total_units": total_units,
            "x_center": x_center,
            "y_center": y_center,
            "x_size": x_size,
            "y_size": y_size
        }
        super().__init__(params)


class LocationAddGateway(LocationCommand):
    def __init__(self, datacenter: str, room: str, gateway: str,
            device_id: str, mesh_id: str, x: float, y: float, z: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "gateway": gateway,
            "device_id": device_id,
            "mesh_id": mesh_id,
            "x": x,
            "y": y,
            "z": z
        }
        super().__init__(params)


class LocationAddNode(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str, rack: str,
            node: str, mac: str, mesh_id: str, uuid: str, unit: int,
            source: str, x: float, y: float, z: float):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "rack": rack,
            "node": node,
            "mac": mac,
            "mesh_id": mesh_id,
            "uuid": uuid,
            "unit": unit,
            "source": source,
            "x": x,
            "y": y,
            "z": z
        }
        super().__init__(params)


class LocationDelRoom(LocationCommand):
    def __init__(self, datacenter: str, room: str):
        params = {
            "datacenter": datacenter,
            "room": room
        }
        super().__init__(params)


class LocationDelRow(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row
        }
        super().__init__(params)


class LocationDelContainer(LocationCommand):
    def __init__(self, datacenter: str, room: str, container: str):
        params = {
            "datacenter": datacenter,
            "room": room,
            "container": container
        }
        super().__init__(params)


class LocationDelRack(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str, rack: str):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "rack": rack
        }
        super().__init__(params)


class LocationDelGateway(LocationCommand):
    def __init__(self, datacenter: str, room: str, gateway: str):
        params = {
            "datacenter": datacenter,
            "room": room,
            "gateway": gateway
        }
        super().__init__(params)


class LocationDelNode(LocationCommand):
    def __init__(self, datacenter: str, room: str, row: str, rack: str,
            node: str):
        params = {
            "datacenter": datacenter,
            "room": room,
            "row": row,
            "rack": rack,
            "node": node
        }
        super().__init__(params)


class LocationImportRoom(LocationCommand):
    def __init__(self, datacenter: str, room_file: str):
        params = {
            "datacenter": datacenter,
            "room_file": room_file
        }
        super().__init__(params)


class LocationImportGenesis(LocationCommand):
    def __init__(self, genesis_file: str):
        params = {
            "genesis_file": genesis_file
        }
        super().__init__(params)


class SimulatorCommand(Command):
    """ Base simulator command. Should not be instantiated. """


class SimulatorStart(SimulatorCommand):
    """ Starts the simulator.

    :param period: Sending rate period, in seconds.
    :type period: int
    :param n_nodes: Number of simulated nodes.
    :type n_nodes: int
    :param seed: Random generator seed.
    :type seed: str
    """
    def __init__(self, period: int, n_nodes: int, seed: str=""):
        params = {
            "period": period,
            "n_nodes": n_nodes,
            "seed": seed,
        }
        super().__init__(params)


class SimulatorStop(SimulatorCommand):
    """ Stop the simulator. """
    def __init__(self):
        super().__init__({})


class SimulatorStatus(SimulatorCommand):
    """ Simulator status.

    Response extra data:
        running: bool
        period: int
        n_nodes: int
    """
    def __init__(self):
        super().__init__({})


class BackendCommand(Command):
    """ Base Backend command. Should not be instantiated. """


class BackendGetNodes(BackendCommand):
    """ Get and store backend nodes.
    """
    def __init__(self):
        super().__init__({})


class ThreadList(Command):
    """ Gets the list of active threads.
    """
    def __init__(self):
        super().__init__({})
