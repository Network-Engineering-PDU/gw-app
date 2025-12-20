from enum import Enum, auto


class EventType(Enum):
    # Virtual nodes
    VIRTUAL_MEDIAN = auto()
    VIRTUAL_MAX = auto()
    VIRTUAL_MIN = auto()
    VIRTUAL_MAX_NO_OUTLIERS = auto()
    VIRTUAL_MIN_NO_OUTLIERS = auto()
    VIRTUAL_WEIGHTED_SUM = auto()
    VIRTUAL_BACKEND_GET = auto()
    VIRTUAL_SNMP_GET = auto()
    VIRTUAL_MODBUS_GET = auto()
    FAULT_TEMP_DATA = auto()
    FAULT_PWMT_DATA = auto()
    BACKUP_PUT = auto()
    STOP_GATEWAY = auto()


class Event:
    def __init__(self, event_type):
        self.event_type = event_type
