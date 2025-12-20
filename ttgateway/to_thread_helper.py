import asyncio
import functools
import contextvars
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

async def to_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    func_name = func.__name__
    #logger.info(f"New to_thread {func_name}")
    executor = ThreadPoolExecutor(max_workers=1,
                                  thread_name_prefix=func_name)
    # pylint: disable=bare-except
    try:
        ret = await loop.run_in_executor(executor, func_call)
    except:
        logger.error("Error in to_thread rutine")
        executor.shutdown()
        raise
    # pylint: enable=bare-except

    #logger.info(f"Stop to_thread {func_name}")
    executor.shutdown()
    return ret

#   with ThreadPoolExecutor(max_workers=1,
#             thread_name_prefix=func_name) as executor:
#       ret = await loop.run_in_executor(executor, func_call)
