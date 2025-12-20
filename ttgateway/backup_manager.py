import os
import time
import json
import asyncio
import logging

from ttgateway.config import config
from ttgateway.events import EventType, Event

logger = logging.getLogger(__name__)

class BackupPut(Event):
    """ Backup put event. """
    def __init__(self, backup):
        super().__init__(EventType.BACKUP_PUT)
        self.backup = backup

class BackupManager:
    def __init__(self, name, event_handler):
        self.name = name
        self.event_handler = event_handler
        self.dir = f"{config.TT_DIR}/.backups/{self.name}"
        self.backups = []

    def __len__(self):
        return len(self.backups)

    def pending(self):
        return bool(len(self))

    def _start(self):
        os.makedirs(self.dir, exist_ok=True)
        for file in os.listdir(self.dir):
            if file == "current.bb" or not file.endswith(".bb"):
                continue
            try:
                self.backups.append(int(file[:-len(".bb")]))
            except ValueError:
                logger.warning(f"Invalid backup file: {self.dir}/{file}")
                continue

    async def start(self):
        await asyncio.to_thread(self._start)

    def _get_current(self):
        file = f"{self.dir}/current.bb"
        if not os.path.isfile(file):
            return None
        with open(file) as f:
            try:
                backup = json.load(f)
            except json.JSONDecodeError:
                logger.debug(f"Error getting current: {file}")
                os.remove(file)
                return None
        os.remove(file)
        return backup

    async def get_current(self):
        return await asyncio.to_thread(self._get_current)

    def _save_current(self, backup):
        with open(f"{self.dir}/current.bb", "w") as f:
            json.dump(backup, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    async def save_current(self, backup):
        await asyncio.to_thread(self._save_current, backup)

    def _put(self, backup):
        ts = int(time.time())
        with open(f"{self.dir}/{ts}.bb", "w") as f:
            json.dump(backup, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        self.backups.append(ts)

    def put_blocking(self, backup):
        self._put(backup)

    async def put(self, backup):
        await asyncio.to_thread(self._put, backup)
        await self.event_handler.send_event(BackupPut(backup))

    def _get(self):
        if len(self) == 0:
            return None
        ts = self.backups[0]
        file = f"{self.dir}/{ts}.bb"
        if not os.path.isfile(file):
            return None
        with open(file) as f:
            try:
                backup = json.load(f)
            except json.JSONDecodeError:
                logger.debug(f"Error getting {self.dir}/{ts}.bb")
                return None
        return backup

    async def get(self):
        return await asyncio.to_thread(self._get)

    def _pop(self):
        if len(self) == 0:
            return None
        error_loading = False
        ts = self.backups[0]
        file = f"{self.dir}/{ts}.bb"
        if not os.path.isfile(file):
            self.backups.pop(0)
            return None
        with open(file) as f:
            try:
                backup = json.load(f)
            except json.JSONDecodeError:
                logger.debug(f"Error popping {self.dir}/{ts}.bb")
                error_loading = True
        os.remove(file)
        self.backups.pop(0)
        if error_loading:
            return None
        return backup

    async def pop(self):
        return await asyncio.to_thread(self._pop)
