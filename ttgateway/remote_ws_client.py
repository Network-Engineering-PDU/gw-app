import json
import hmac
import asyncio
import logging

import websockets

import ttgateway.commands as cmds
from ttgateway.config import config


logger = logging.getLogger(__name__)


class RemoteWebsocketClient:
    PING_INTERVAL = 120 # 2 min
    def __init__(self, server):
        self.server = server
        self.task = None
        self.running = False
        self.headers = {}

    @property
    def url(self) -> str:
        return config.remote_client.url

    @property
    def key(self) -> bytes:
        return config.remote_client.hmac_key.encode()

    @property
    def msg(self) -> bytes:
        return config.remote_client.hmac_msg.encode()

    @property
    def device(self) -> str:
        return f"{config.backend.company}_{config.backend.device_id.upper()}"

    def get_server_url(self):
        return self.url + "/development/?deviceID=" + self.device

    def generate_headers(self):
        h = hmac.new(key=self.key, msg=self.msg, digestmod="sha1")
        self.headers["authorizationToken"] = h.hexdigest()

    def start(self):
        if not self.running:
            logger.info("Starting remote client")
            self.generate_headers()
            self.task = asyncio.create_task(self.run())
            self.running = True

    def stop(self):
        if self.task and self.running:
            logger.info("Stopping remote client")
            self.task.cancel()
            self.running = False

    async def run(self):
        async for websocket in websockets.connect(self.get_server_url(),
                extra_headers=self.headers, ping_interval=self.PING_INTERVAL):
            logger.debug("Websocket client connected")
            try:
                while True:
                    raw_msg = await websocket.recv()
                    msg = json.loads(raw_msg)
                    cmd = json.dumps(msg["command"]).encode()

                    command = cmds.SerialMessage.deserialize(cmd)
                    if not command:
                        logger.debug("Unknown command received")
                        continue
                    rsp = await self.server.process_command(command)
                    # Remove the first 4 bytes (length), encode as json
                    rsp_payload = json.loads(rsp.serialize()[4:].decode())

                    store_command = {
                        "action": "storeCommand",
                        "deviceID": self.device,
                        "deviceResponse": rsp_payload,
                    }
                    await websocket.send(json.dumps(store_command))
                    rsp = await websocket.recv()

            except websockets.ConnectionClosed:
                logger.info("Websocket closed, reconnecting...")
                await asyncio.sleep(5)
            except asyncio.exceptions.CancelledError:
                logger.info("Websocket closed")
                return
            except json.JSONDecodeError:
                logger.info("Unknown command received: invalid JSON")
                await asyncio.sleep(1)
            except:
                logger.exception("Websocket exception")
                raise
