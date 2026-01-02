import logging
import asyncio

from ttraft.transport import TransportInterface


logger = logging.getLogger(__name__)


class UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, recv_callback):
        self.recv_callback = recv_callback

    def connection_made(self, transport):
        pass
        #self.transport = transport

    def datagram_received(self, data, addr):
        self.recv_callback(data, addr)

    def error_received(self, exc):
        logger.error(f"UPD error received {exc}")

    def connection_lost(self, exc):
        logger.info(f"UDP connection lost {exc}")


class UdpTransport(TransportInterface):
    PORT = 34567
    def __init__(self, address):
        self.address, self.port = self.split_address_port(address)
        self.protocol = UdpProtocol(self.recv_callback)
        self.recv_queue = asyncio.Queue()
        self.transport = None

    @classmethod
    def split_address_port(cls, address):
        if ":" in address:
            address, port = address.split(":")
            return (address, int(port))
        return (address, cls.PORT)

    @classmethod
    def join_address_port(cls, address):
        if address[1] == cls.PORT:
            return address[0]
        return ":".join((address[0], str(address[1])))

    def recv_callback(self, data, sender):
        self.recv_queue.put_nowait((data, self.join_address_port(sender)))

    async def recv(self):
        return await self.recv_queue.get()

    async def send(self, data, dest):
        self.transport.sendto(data, self.split_address_port(dest))

    async def start(self):
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
                lambda: self.protocol, (self.address, self.port))

    async def stop(self):
        if self.transport is not None:
            self.transport.close()
