from enum import Enum
import logging
import base64

from ttgwlib.node import Node
from ttgwlib.events.model_events import ModelEvent
from ttgwlib import EventType as LibEventType
from ttraft.state_machine import StateMachine

from ttgateway.events import EventType, Event
from ttgateway.gateway.sqlite_database import SqliteDatabase


logger = logging.getLogger(__name__)


class FaultTempData(Event):
    """ Fault telemetry event. """
    def __init__(self, node, data):
        super().__init__(EventType.FAULT_TEMP_DATA)
        self.node = node
        self.data = data


class FaultPwmtData(Event):
    """ Fault PWMT event. """
    def __init__(self, node, data):
        super().__init__(EventType.FAULT_PWMT_DATA)
        self.node = node
        self.data = data


class RaftCmds(Enum):
    """ Raft commands. """
    UPDATE_NODE = 1
    REMOVE_NODE = 2
    UPDATE_TELE = 3
    UPDATE_PWMT = 4
    SAVE_BACKUP = 5


class RaftSqliteDatabase(SqliteDatabase, StateMachine):
    RAFT_LOG_LVL = 9
    def __init__(self, database_file, fault_manager):
        super().__init__(database_file)
        self.fault_manager = fault_manager

    def store_node(self, node):
        if self.fault_manager.is_started and self.fault_manager.module:
            node_json = node.to_json()
            del node_json["sleep_timestamp"]
            del node_json["msg_timestamp"]
            self.fault_manager.send((RaftCmds.UPDATE_NODE.value, node_json))
        else:
            if node in self.node_list:
                self.node_list[self.node_list.index(node)] = node
            else:
                self.node_list.append(node)
            self.store_node_db(node)

    def remove_node(self, node):
        if self.fault_manager.is_started and self.fault_manager.module:
            node = {"mac": node.mac.hex()}
            self.fault_manager.send((RaftCmds.REMOVE_NODE.value, node))
        else:
            if node in self.node_list:
                self.node_list.remove(node)
                self.remove_node_db(node)

    def update_telemetry(self, event):
        if self.fault_manager.is_started and self.fault_manager.module:
            serial_event = {
                "mac": event.node.mac.hex(),
                "data": event.data
            }
            logger.log(self.RAFT_LOG_LVL, "Send update telemetry event")
            self.fault_manager.send((RaftCmds.UPDATE_TELE.value, serial_event))

    def update_pwmt(self, event):
        if self.fault_manager.is_started and self.fault_manager.module:
            serial_event = {
                "mac": event.node.mac.hex(),
                "data": event.data
            }
            logger.log(self.RAFT_LOG_LVL, "Send update pwmt event")
            self.fault_manager.send((RaftCmds.UPDATE_PWMT.value, serial_event))

    def save_backup(self, event):
        if self.fault_manager.is_started and self.fault_manager.module:
            logger.log(self.RAFT_LOG_LVL, "Send save backup event")
            self.fault_manager.send((RaftCmds.SAVE_BACKUP.value, event.backup))

    def apply_command(self, command):
        """ Commands:
        (RaftCmds.UPDATE_NODE, {"mac": mac, ...}) -> update node
        (RaftCmds.REMOVE_NODE, {"mac": mac})      -> remove node
        (RaftCmds.UPDATE_TELE, serialized_event)  -> update telemetry
        (RaftCmds.UPDATE_PWMT, serialized_event)  -> update pwmt data
        (RaftCmds.SAVE_BACKUP, backup)            -> save backup
        """
        try:
            cmd_type, cmd_data = command
        except ValueError:
            return
        logger.log(self.RAFT_LOG_LVL, f"Raft cmd rx: {cmd_type}, {cmd_data}")
        if cmd_type == RaftCmds.UPDATE_NODE.value:
            node = Node.from_json(cmd_data)
            if node in self.node_list:
                self.node_list[self.node_list.index(node)] = node
            else:
                self.node_list.append(node)
            self.store_node_db(node)
        elif cmd_type == RaftCmds.REMOVE_NODE.value:
            for node in self.node_list:
                if node.mac.hex() == cmd_data["mac"]:
                    self.node_list.remove(node)
                    self.remove_node_db(node)
                    break
        elif cmd_type == RaftCmds.UPDATE_TELE.value:
            if (self.fault_manager.is_started and self.fault_manager.module and
                    self.fault_manager.module.is_leader()):
                return
            node = self.get_node_by_mac(bytes.fromhex(cmd_data["mac"]))
            data = cmd_data["data"]
            event = ModelEvent(LibEventType.TEMP_DATA, data, node, None)
            send_event = self.fault_manager.event_handler.process_event
            logger.log(self.RAFT_LOG_LVL, f"send_tel_event: {event.data}")
            send_event(event)
        elif cmd_type == RaftCmds.UPDATE_PWMT.value:
            if (self.fault_manager.is_started and self.fault_manager.module and
                    self.fault_manager.module.is_leader()):
                return
            node = self.get_node_by_mac(bytes.fromhex(cmd_data["mac"]))
            data = cmd_data["data"]
            event = ModelEvent(LibEventType.PWMT_DATA, data, node, None)
            send_event = self.fault_manager.event_handler.process_event
            logger.log(self.RAFT_LOG_LVL, f"send_pwmt_event: {event.data}")
            send_event(event)
        elif cmd_type == RaftCmds.SAVE_BACKUP.value:
            if (self.fault_manager.is_started and self.fault_manager.module and
                    self.fault_manager.module.is_leader()):
                return
            app_manager = self.fault_manager.server.app_manager
            backup_put = app_manager.interfaces["backend"].backup.put_blocking
            logger.log(self.RAFT_LOG_LVL, f"save_back_func: {cmd_data}")
            backup_put(cmd_data)

    def apply_snapshot(self, snapshot):
        address = self.get_address()
        netkey = self.get_netkey()
        self.stop()
        sql_db = base64.b64decode(snapshot)
        with open(self.database_file, "wb") as f:
            f.write(sql_db)
        self.start()
        self.set_address(address)
        self.set_netkey(netkey)

    def get_snapshot(self):
        with open(self.database_file, "rb") as f:
            sql_db = f.read()
        return base64.b64encode(sql_db).decode("utf-8")
