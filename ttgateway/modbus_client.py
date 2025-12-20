import asyncio
import logging
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

import ttgateway.commands as cmds


logger = logging.getLogger(__name__)


class ModbusClient:
    def read_coils(self, host: str, port: int, address: int, slave: int):
        """ Returns int. """
        try:
            client = ModbusTcpClient(host, port)
            client.connect()
            result = client.read_coils(address, 1, slave).bits[0]
            client.close()
            return result
        except ConnectionException:
            logger.error("Connection error. Invalid host.")
            return None

    def read_discrete_inputs(self, host: str, port: int, address: int,
            slave: int):
        """ Returns int. """
        try:
            client = ModbusTcpClient(host, port)
            client.connect()
            result = client.read_discrete_inputs(address, 1, slave).bits[0]
            client.close()
            return result
        except ConnectionException:
            logger.error("Connection error. Invalid host.")
            return None

    def read_holding_registers(self, host: str, port: int, address: int,
            slave: int):
        """ Returns int. """
        try:
            client = ModbusTcpClient(host, port)
            client.connect()
            result = client.read_holding_registers(
                address, 1, slave).getRegister(0)
            client.close()
            return result
        except ConnectionException:
            logger.error("Connection error. Invalid host.")
            return None

    def read_input_registers(self, host: str, port: int, address: int,
            slave: int):
        """ Returns int. """
        try:
            client = ModbusTcpClient(host, port)
            client.connect()
            result = client.read_input_registers(
                address, 1, slave).getRegister(0)
            client.close()
            return result
        except ConnectionException:
            logger.error("Connection error. Invalid host.")
            return None

    async def process_command(self, command):
        if isinstance(command, cmds.ModbusReadCoils):
            rsp = await asyncio.to_thread(self.read_coils, command.host,
                command.port, command.address, command.slave)
            if rsp is None:
                return command.response("Modbus error", False)
            return command.response(extra_data={"response": rsp})

        if isinstance(command, cmds.ModbusReadDiscreteInputs):
            rsp = await asyncio.to_thread(self.read_discrete_inputs,
                command.host, command.port, command.address, command.slave)
            if rsp is None:
                return command.response("Modbus error", False)
            return command.response(extra_data={"response": rsp})

        if isinstance(command, cmds.ModbusReadHoldingRegisters):
            rsp = await asyncio.to_thread(self.read_holding_registers,
                command.host, command.port, command.address, command.slave)
            if rsp is None:
                return command.response("Modbus error", False)
            return command.response(extra_data={"response": rsp})

        if isinstance(command, cmds.ModbusReadInputRegisters):
            rsp = await asyncio.to_thread(self.read_input_registers,
                command.host, command.port, command.address, command.slave)
            if rsp is None:
                return command.response("Modbus error", False)
            return command.response(extra_data={"response": rsp})

        logger.warning("Unknown Modbus command")
        return command.response("Unknown Modbus command", False)
