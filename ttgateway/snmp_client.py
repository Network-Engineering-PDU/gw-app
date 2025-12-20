import asyncio
import logging
import netsnmp

import ttgateway.commands as cmds


logger = logging.getLogger(__name__)


class SnmpClient:
    NUMERIC_TYPES = ("INTEGER", "COUNTER", "TICKS", "GAUGE", "COUNTER64")
    STRING_TYPES = ("OCTETSTR", "IPADDR", "OBJECTID")

    def check_oid_input(self, oid: str):
        if not oid:
            return False

        oid_start = ".1"
        if len(oid) >= len(oid_start) and oid[:len(oid_start)] == oid_start:
            return True
        return False

    def covert_rsp_value(self, obj: netsnmp.Varbind):
        if obj.type in self.NUMERIC_TYPES:
            return int(obj.val)
        if obj.type in self.STRING_TYPES:
            if isinstance(obj.val, str):
                return obj.val
            if isinstance(obj.val, bytes):
                return obj.val.decode()
            return str(obj.val)
        if obj.type == "NOSUCHOBJECT":
            return None
        if obj.type is None:
            return None
        return str(obj)

    def get(self, host: str, community: str, oid: str, version: int=2):
        """ Returns Tuple(type: str, value: str|int|None). """
        session = netsnmp.Session(DestHost=host, Community=community,
            Version=version)
        obj = netsnmp.Varbind(oid)
        session.get(netsnmp.VarList(obj))
        return (obj.type, self.covert_rsp_value(obj))

    def walk(self, host: str, community: str, base_oid: str, version: int=2):
        """ Returns List[Tuple(oid: str, type: str, value: str|int|None)]. """
        session = netsnmp.Session(DestHost=host, Community=community,
            Version=2)
        session.UseLongNames = 1
        # session.UseNumeric = 1 # Bug
        obj_list = netsnmp.VarList(base_oid)
        session.walk(obj_list)
        results = []
        for obj in obj_list:
            results.append((obj.tag, obj.type, self.covert_rsp_value(obj)))
        return results

    async def process_command(self, command):
        if isinstance(command, cmds.SnmpGet):
            if not self.check_oid_input(command.oid):
                return command.response("Invalid OID", False)
            rsp = await asyncio.to_thread(self.get, command.host,
                command.community, command.oid, command.version)
            if rsp[0] is None:
                return command.response("Invalid host or community", False)
            return command.response(extra_data={"response": rsp})

        if isinstance(command, cmds.SnmpWalk):
            if not self.check_oid_input(command.oid):
                return command.response("Invalid OID", False)
            rsp = await asyncio.to_thread(self.walk, command.host,
                command.community, command.oid, command.version)
            return command.response(extra_data={"response": rsp})


        logger.warning("Unknown SNMP command")
        return command.response("Unknown SNMP command", False)
