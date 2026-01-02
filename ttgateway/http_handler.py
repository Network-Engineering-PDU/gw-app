import asyncio
import logging

from ttgateway.http_helper import HttpHelper
from ttgateway.config import config


class HttpHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []
        self.http_helper = HttpHelper()
        self.started = False
        self.send_task = None

    @property
    def url(self):
        return config.http_logging.url

    @property
    def period(self):
        return config.http_logging.period

    @property
    def backend_company(self):
        return config.backend.company

    @property
    def backend_device_id(self):
        return config.backend.device_id

    def start(self):
        if not self.started:
            self.started = True
            self.send_task = asyncio.create_task(self.send())

    def stop(self):
        if self.started:
            self.started = False
            if self.send_task:
                self.send_task.cancel()

    def emit(self, record):
        if record.name == "ttgateway.http_helper":
            return
        if record.levelno == 25:
            level = "INFO"
        else:
            level = record.levelname
        self.logs.append({
            "timestamp": record.asctime,
            "level": level,
            "module": record.name,
            "msg": record.message
        })

    async def send(self):
        while True:
            await asyncio.sleep(self.period)
            self.acquire()
            logs = self.logs.copy()
            self.release()

            if not logs:
                continue

            body = {
                "company": self.backend_company,
                "device_id": self.backend_device_id,
                "logs": logs,
            }
            rsp = await self.http_helper.request("Logging", "POST", self.url,
                body)
            if rsp and rsp.ok:
                self.acquire()
                self.logs = self.logs[len(logs):]
                self.release()

    def flush(self):
        pass
