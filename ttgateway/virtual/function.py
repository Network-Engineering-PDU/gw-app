import asyncio

from ttgateway import utils


class BaseFunction:
    def __init__(self, event_handler, handlers):
        self.event_handler = event_handler
        self.handlers = handlers
        self.task = None

    async def run(self):
        raise NotImplementedError

    def to_json(self):
        """ The dict must include the following fields:
         - name: str
         - params: List
        """
        raise NotImplementedError

    async def send_event(self, event):
        await self.event_handler.send_event(event)

    def start(self):
        for event_type, handler in self.handlers:
            self.event_handler.add_handler(event_type, handler)
        self.task = asyncio.create_task(self.run())

    def stop(self):
        if self.task is not None:
            for _, handler in self.handlers:
                self.event_handler.remove_handler(handler)
            self.task.cancel()

    def get_event_handlers(self):
        return self.handlers

    def __str__(self):
        name = self.__class__.__name__[:-len("Function")]
        return utils.camel_to_snake(name)

    def __repr__(self):
        return self.__str__()

    @classmethod
    def name(cls):
        name = cls.__name__[:-len("Function")]
        return utils.camel_to_snake(name)
