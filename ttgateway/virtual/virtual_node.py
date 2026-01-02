import os

from ttgwlib import Node


class VirtualNode(Node):
    COMPANY_ID = 0xDA51
    BOARD_ID = 0xFFF0
    BASE_UNICAST_ADDRESS_LOCAL = 0x7800

    def __init__(self, address: int, name: str=None, mac: bytes=None,
            uuid: bytes=None, function=None):
        self.address = address
        if mac is None:
            mac = os.urandom(6)
        if uuid is None:
            uuid = bytearray([self.COMPANY_ID >> 8, self.COMPANY_ID & 0xFF,
                self.BOARD_ID >> 8, self.BOARD_ID & 0xFF,
                0xFF, 0xFF, 0xFF, 0xFF])
            uuid += os.urandom(8)
            uuid = bytes(uuid)
        if name is None:
            name = f"virtual_sensor_{self.address}"
        super().__init__(mac, uuid, self.address, name)
        self.function = function
        self.updated_ts = 0

    @property
    def board_id(self) -> int:
        return self.BOARD_ID

    def is_local(self) -> bool:
        return self.address >= self.BASE_UNICAST_ADDRESS_LOCAL

    def is_low_power(self) -> bool:
        return False

    def has_co2(self) -> bool:
        return False

    def has_iaq(self) -> bool:
        return False

    def to_json(self):
        return {
            "name": self.name,
            "address": self.address,
            "mac": self.mac.hex(),
            "uuid": self.uuid.hex(),
            "updated": self.updated_ts,
            "function": self.function.to_json()
        }
