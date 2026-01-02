import asyncio
import logging
from ttgateway.events import EventType, Event


logger = logging.getLogger(__name__)


class EventHandler:
    def __init__(self, led_controller):
        self.event_queue = asyncio.Queue()
        self.loop = asyncio.get_event_loop()
        self.handlers = {}
        self.event_types = set()
        self.event_types.add(EventType.STOP_GATEWAY)
        self.led_controller = led_controller
        self.event_filter = None

    def process_event(self, event):
        async def async_store_event(event):
            if self.event_filter and not self.event_filter(event):
                return
            if event.event_type not in self.event_types:
                return
            self.log_event(event)
            await self.event_queue.put(event)
            asyncio.create_task(asyncio.to_thread(self.led_blink))
        asyncio.run_coroutine_threadsafe(async_store_event(event),
            self.loop)

    async def send_event(self, event):
        if event.event_type in self.event_types:
            await self.event_queue.put(event)

    def add_handler(self, event_type, event_handler):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(event_handler)
        self.event_types.add(event_type)

    def add_event_filter(self, event_filter):
        self.event_filter = event_filter

    def remove_event_filter(self):
        self.event_filter = None

    def remove_handler(self, event_handler):
        for event_type, event_handlers in self.handlers.items():
            if event_handler in event_handlers:
                event_handlers.remove(event_handler)
                if not event_handlers:
                    self.event_types.remove(event_type)


    async def stop_handler(self):
        stop_event = Event(EventType.STOP_GATEWAY)
        await self.send_event(stop_event)

    async def run_handlers(self):
        while True:
# pylint: disable=bare-except
            handler = None
            try:
                event = await self.event_queue.get()
                if event.event_type in self.handlers:
                    for handler in self.handlers[event.event_type]:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            await asyncio.to_thread(handler, event)
            except:
                if handler is not None:
                    logger.exception(f"Handler error ({handler.__name__})")
                else:
                    logger.exception("Handler error")

            if event.event_type == EventType.STOP_GATEWAY:
                break
# pylint: enable=bare-except
        logger.info("Event handler disabled")

    def led_blink(self):
        self.led_controller.mesh_rx()

    def log_event(self, event):
        log = f"Event: {event.event_type.name}"
        if hasattr(event, "node"):
            log += f", {event.node}"
        logger.debug(log)
