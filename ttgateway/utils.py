import os
import time
import math
import socket
import logging
import logging.handlers
import asyncio
import threading
import random
import requests

from ttgateway.config import config


def periodic_task(function, period, *args, **kwargs):
    return periodic_task_delay(function, period, 0, *args, **kwargs)

def periodic_task_delay(function, period, delay, *args, **kwargs):
    logger = logging.getLogger("periodic_task")
    async def periodic_task_coro(function, period, delay, *args, **kwargs):
        if delay > 0:
            await asyncio.sleep(delay)
        next_time = time.monotonic()
        while True:
            next_time += period
            try:
                if asyncio.iscoroutinefunction(function):
                    await asyncio.create_task(function(*args, **kwargs))
                else:
                    function(*args, **kwargs)
            except asyncio.CancelledError:
                return
            except:
                logger.exception(f"Periodic task {function.__name__} ex")
                raise
            await asyncio.sleep(next_time - time.monotonic())
    task = asyncio.create_task(periodic_task_coro(function, period, delay,
        *args, **kwargs))
    task.set_name(function.__qualname__)
    return task


def non_periodic_task(function, delay, *args, **kwargs):
    logger = logging.getLogger("non_periodic_task")
    async def non_periodic_task_coro(function, delay, *args, **kwargs):
        await asyncio.sleep(delay)
        try:
            if asyncio.iscoroutinefunction(function):
                await asyncio.create_task(function(*args, **kwargs))
            else:
                function(*args, **kwargs)
        except asyncio.CancelledError:
            return
        except:
            logger.exception(f"Non periodic task {function.__name__} ex")
            raise
    return asyncio.create_task(non_periodic_task_coro(function, delay, *args,
        **kwargs))


def config_logger(docker=False):
    """ Configures the application logger."""
    os.makedirs(config.TT_DIR + "/logs", exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - ' +
        '%(levelname)s - %(message)s')
    if docker:
        fh = logging.StreamHandler()
    else:
        fh = logging.handlers.RotatingFileHandler(os.path.join(config.TT_DIR,
            'logs', "log"), maxBytes=1024*1024*10, backupCount=100)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # Supress third party loggers
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("botocore").setLevel(logging.INFO)
    logging.getLogger("s3trasnfer").setLevel(logging.INFO)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("ttraft").setLevel(logging.INFO)


def set_threading_exception_handler():
    threading.excepthook = _threading_exception_handler


def _threading_exception_handler(exc_type, exc_value, exc_traceback):
    """ Function to override the threading exception handler with one
    that logs the exception with logging.
    """
    logger = logging.getLogger("threading")
    logger.error("Uncaught threading exception",
            exc_info=(exc_type, exc_value, exc_traceback))

def delta_to_timestr(delta):
    h, rem = divmod(delta.seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except (OSError, TimeoutError):
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def camel_to_snake(s):
    return "".join(["_"+c.lower() if c.isupper() else c for c in s]).lstrip("_")


def snake_to_camel(s, first=False):
    words = s.split("_")
    if first:
        return "".join(w.title() for w in words)
    return words[0] + "".join(w.title() for w in words[1:])


def check_internet_connection():
    try:
        rsp = requests.get("http://nmcheck.gnome.org/check_network_status.txt",
            timeout=20)
        if rsp.ok and rsp.content == b'NetworkManager is online\n':
            return True
        return False
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False

def tail(path, lines=10):
    if os.path.isfile(path):
        block_size = os.statvfs(path).f_bsize
        file = open(path, "rb")
        file.seek(0, 2)
        block_end_byte = file.tell()
        lines_to_go = lines
        block_number = -1
        blocks = []
        while lines_to_go > 0 and block_end_byte > 0:
            if (block_end_byte - block_size) > 0:
                file.seek(block_number * block_size, 2)
                blocks.append(file.read(block_size))
            else:
                file.seek(0,0)
                blocks.append(file.read(block_end_byte))
            lines_found = blocks[-1].count(b'\n')
            lines_to_go -= lines_found
            block_end_byte -= block_size
            block_number -= 1
        all_read_text = b"".join(reversed(blocks))
        file.close()
        return b"\n".join(all_read_text.splitlines()[-lines:])
    return b""

def percentile(data_list, percntl):
    data_len = len(data_list)
    pos = data_len * percntl / 100
    if pos.is_integer():
        return sorted(data_list)[int(pos)]
    return sorted(data_list)[int(math.ceil(pos)) - 1]

async def shell(cmd, timeout=None):
    retval, output = None, None
    if isinstance(cmd, list):
        try:
            process = await asyncio.create_subprocess_exec(*cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
        except FileNotFoundError:
            return -1, "Command not found"
    elif isinstance(cmd, str):
        try:
            process = await asyncio.create_subprocess_shell(cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
        except FileNotFoundError:
            return -1, "Command not found"
    else:
        raise TypeError(f"Invalid cmd type {type(cmd)}: must be list or str")
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
        output = stdout.decode()
        retval = process.returncode
    except asyncio.TimeoutError:
        process.kill()
    return retval, output

async def ntp_is_sync():
    retval, output = await shell("chronyc tracking")
    if retval != 0:
        return False
    for line in output.splitlines():
        if "Ref time (UTC)" in line:
            return not "Thu Jan 01 00:00:00 1970" in line
    return False

async def ntp_restart():
    retval, _ = await shell("/etc/init.d/chronyd restart")
    return retval

def gen_randbytes(number):
    return bytes([random.getrandbits(8) for i in range(number)])
