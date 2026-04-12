EVENT_TICK = "eTick"
EVENT_TIMER = "eTimer"

class Event:
    def __init__(self, type: str, data: dict = None):
        self.type = type
        self.data = data if data else {}

class EventEngine:
    def __init__(self):
        self._handlers = {}

    def register(self, event_type: str, handler: callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unregister(self, event_type: str, handler: callable):
        if event_type in self._handlers:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)
            if not self._handlers[event_type]:
                del self._handlers[event_type]

    def process(self, event: Event):
        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                handler(event)
