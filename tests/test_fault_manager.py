import asyncio
import unittest
from unittest.mock import Mock, patch

from ttgateway.fault_tolerance.fault_manager import FaultManager


def make_fault_manager():
    """Builds a FaultManager with a minimal mock server.

    FaultManager.__init__ only needs server.event_handler.add_handler(...)
    to exist and ttraft.Config() to construct successfully; neither actually
    starts any networking, so a bare Mock server is sufficient here.
    """
    server = Mock()
    server.event_handler = Mock()
    return FaultManager(server)


class WaitForInternetConnectionTest(unittest.IsolatedAsyncioTestCase):
    """Regression tests for CRIT-4: wait_for_internet_connection() used to
    call asyncio.sleep(2) without awaiting it (a no-op) and ran the blocking
    check_internet_connection() directly on the event loop, so a down/slow
    connectivity check could stall the whole daemon for up to ~20 minutes.

    retries/delay are now injectable specifically so these tests don't have
    to exercise (or wait out) the real production schedule.
    """

    async def test_returns_false_after_exhausting_injected_retries(self):
        fm = make_fault_manager()
        with patch("ttgateway.fault_tolerance.fault_manager.utils"
                   ".check_internet_connection", return_value=False) as check:
            check.__name__ = "check_internet_connection"
            result = await asyncio.wait_for(
                fm.wait_for_internet_connection(retries=3, delay=0.01),
                timeout=5,
            )
        self.assertFalse(result)
        # 1 initial attempt + 3 retries = 4 calls total.
        self.assertEqual(check.call_count, 4)

    async def test_returns_true_once_connection_succeeds(self):
        fm = make_fault_manager()
        results = iter([False, True])
        with patch("ttgateway.fault_tolerance.fault_manager.utils"
                   ".check_internet_connection",
                   side_effect=lambda: next(results)) as check:
            check.__name__ = "check_internet_connection"
            result = await asyncio.wait_for(
                fm.wait_for_internet_connection(retries=3, delay=0.01),
                timeout=5,
            )
        self.assertTrue(result)
        self.assertEqual(check.call_count, 2)

    async def test_does_not_block_the_event_loop(self):
        """The original bug ran the blocking `requests.get` call directly on
        the event loop. If that regresses, a concurrent heartbeat task will
        stall right along with it instead of ticking on schedule."""
        fm = make_fault_manager()
        heartbeat_ticks = []

        async def heartbeat():
            for _ in range(5):
                await asyncio.sleep(0.01)
                heartbeat_ticks.append(None)

        def slow_blocking_check():
            # Simulates a slow synchronous network call. If this ever runs
            # directly on the event loop again, the heartbeat above will be
            # starved and heartbeat_ticks will end up short.
            import time
            time.sleep(0.2)
            return False

        with patch("ttgateway.fault_tolerance.fault_manager.utils"
                   ".check_internet_connection",
                   side_effect=slow_blocking_check) as check:
            check.__name__ = "check_internet_connection"
            await asyncio.gather(
                asyncio.wait_for(
                    fm.wait_for_internet_connection(retries=0, delay=0.01),
                    timeout=5,
                ),
                heartbeat(),
            )

        self.assertEqual(len(heartbeat_ticks), 5)

    async def test_default_parameters_match_original_production_values(self):
        """Guards against silently changing the real (non-test) retry
        schedule while making it injectable."""
        fm = make_fault_manager()
        import inspect
        sig = inspect.signature(fm.wait_for_internet_connection)
        self.assertEqual(sig.parameters["retries"].default, 60)
        self.assertEqual(sig.parameters["delay"].default, 2)


if __name__ == "__main__":
    unittest.main()
