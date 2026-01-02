from ttgateway import utils
from ttgateway.events import EventType, Event
from ttgateway.virtual.function import BaseFunction
from ttgateway.http_helper import HttpHelper
from ttgateway.config import config


class BackendGetEvent(Event):
    def __init__(self, node, backend_data, _type):
        super().__init__(EventType.VIRTUAL_BACKEND_GET)
        self.node = node
        self.data = {}
        self.data["backend_data"] = backend_data
        self.data["type"] = _type
        self.function_task = None


class BackendGetFunction(BaseFunction):
    def __init__(self, event_handler, node, _type: str, data_url: str,
            path: str, period: int):
        self.node = node
        self.type = _type
        self.data_url = data_url
        self.path = path
        self.http = HttpHelper(self.url, self.user, self.password)
        self.period = int(period)
        handlers = []
        super().__init__(event_handler, handlers)
        self.function_task = None

    @property
    def url(self):
        return config.backend.url

    @property
    def user(self):
        return config.backend.user

    @property
    def password(self):
        return config.backend.password

    async def send_backend_get(self):
        rsp = await self.http.request("virtual_backend_get", "GET",
            self.data_url, None, None)
        if rsp is not None and rsp.ok:
            data = rsp.json()
            keys = self.path.split('.')
            for key in keys:
                if isinstance(data, dict) and key in data:
                    data = data[key]
                else:
                    return
            await self.send_event(BackendGetEvent(self.node, data, self.type))
        else:
            return # No available data

    async def run(self):
        self.task = utils.periodic_task(self.send_backend_get, self.period)

    def to_json(self):
        return {
            "name": str(self),
            "type": self.type,
            "url": self.data_url,
        }
