import logging
import asyncio

from ttraft.transport import TransportInterface
from ttgwlib import EventType


logger = logging.getLogger(__name__)


class MeshTransport(TransportInterface):
    def __init__(self, gateway, event_handler):
        self.gateway = gateway
        self.event_handler = event_handler
        self.recv_queue = asyncio.Queue()

    async def data_handler(self, event):
        await self.recv_queue.put((event.data["data"], event.data["src"]))

    async def recv(self):
        return await self.recv_queue.get()

    async def send(self, data, dest):
        if self.gateway.is_started():
            self.gateway.gw.send_msg(dest, data)
        else:
            logger.error("Gateway not started")

    async def start(self):
        self.event_handler.add_handler(EventType.TRANSPORT_RECV,
            self.data_handler)

    async def stop(self):
        self.event_handler.remove_handler(self.data_handler)
