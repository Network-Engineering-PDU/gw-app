import time
import random
import asyncio
import logging

from ttgwlib import Node, EventType
from ttgwlib.events.model_events import ModelEvent

from ttgateway.utils import gen_randbytes
import ttgateway.commands as cmds


logger = logging.getLogger(__name__)


class Simulator:
    DEFAULT_SEED = "Default_simulator_seed"
    START_UNICAST_ADDRESS = 200

    def __init__(self, event_handler):
        self.event_handler = event_handler
        self.next_unicast_address = self.START_UNICAST_ADDRESS
        self.nodes = []
        self.next_event_list = []
        self.period = 0
        self.running = False
        self.task = None
        self.seed = self.DEFAULT_SEED

    def get_new_unicast_address(self) -> int:
        self.next_unicast_address += 1
        return self.next_unicast_address - 1

    def gen_new_node(self) -> Node:
        mac = gen_randbytes(6)
        uuid = bytes.fromhex("da510018ffffffff") + gen_randbytes(8)
        address = self.get_new_unicast_address()
        name = f"sim_node_{address}"
        devkey = gen_randbytes(16)
        return Node(mac, uuid, address, name, devkey)

    def gen_nodes(self, n_nodes: int):
        random.seed(self.seed)
        now = int(time.monotonic())
        for _ in range(n_nodes):
            self.nodes.append(self.gen_new_node())
            self.next_event_list.append(now + random.randint(0, self.period))
        random.seed()

    def gen_temp_data_event(self, node: Node) -> ModelEvent:
        data = {}
        data["temp"] = random.randint(1500, 2500)
        data["hum"] = random.randint(30, 60)
        data["press"] = 10132500 + random.randint(-500000, 500000)
        data["tid"] =  1
        data["rssi"] = random.randint(-70, -30)
        data["ttl"] = 127
        data["src"] = node.unicast_addr
        return ModelEvent(EventType.TEMP_DATA, data, node, None)

    async def run(self):
        try:
            while True:
                await asyncio.sleep(1)
                now = int(time.monotonic())
                for i, next_event in enumerate(self.next_event_list):
                    if next_event <= now:
                        self.next_event_list[i] += self.period
                        event = self.gen_temp_data_event(self.nodes[i])
                        await self.event_handler.send_event(event)
        except asyncio.CancelledError:
            pass

    async def start(self, period, n_nodes):
        if not self.running:
            self.period = period
            await asyncio.to_thread(self.gen_nodes, n_nodes)
            for node in self.nodes:
                logger.debug(node.mac.hex())
            self.running = True
            self.task = asyncio.create_task(self.run())

    def stop(self):
        if self.running:
            self.running = False
            self.nodes.clear()
            self.next_event_list.clear()
            self.period = 0
            if self.task:
                self.task.cancel()

    async def process_command(self, command):
        logger.debug(f"Command received: {type(command).__name__}")
        if isinstance(command, cmds.SimulatorStart):
            if command.seed:
                self.seed = command.seed
            await self.start(command.period, command.n_nodes)
            return command.response("")

        if isinstance(command, cmds.SimulatorStop):
            self.stop()
            return command.response("")

        if isinstance(command, cmds.SimulatorStatus):
            status = {
                "running": self.running,
                "period": self.period,
                "n_nodes": len(self.nodes),
            }
            return command.response(extra_data=status)

        logger.warning("Unknown command")
        return command.response("Unknown command", False)
