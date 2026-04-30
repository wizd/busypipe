from __future__ import annotations

import unittest

from busypipe.scheduler import MinRateScheduler


class MinRateSchedulerTests(unittest.TestCase):
    def test_default_target_is_250_bytes_per_tick(self) -> None:
        scheduler = MinRateScheduler(min_bps=8000, tick_ms=250)

        self.assertEqual(scheduler.target_bytes_per_tick, 250)

    def test_deficit_accounts_for_sent_bytes(self) -> None:
        scheduler = MinRateScheduler(min_bps=8000, tick_ms=250)
        scheduler.record_sent(100)

        self.assertEqual(scheduler.consume_deficit(), 150)
        self.assertEqual(scheduler.consume_deficit(), 250)


if __name__ == "__main__":
    unittest.main()
