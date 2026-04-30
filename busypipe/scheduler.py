from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MinRateScheduler:
    min_bps: int = 8000
    tick_ms: int = 250

    def __post_init__(self) -> None:
        if self.min_bps <= 0:
            raise ValueError("min_bps must be positive")
        if self.tick_ms <= 0:
            raise ValueError("tick_ms must be positive")
        self.bytes_sent_in_tick = 0

    @property
    def target_bytes_per_tick(self) -> int:
        return max(1, (self.min_bps // 8) * self.tick_ms // 1000)

    def record_sent(self, size: int) -> None:
        if size > 0:
            self.bytes_sent_in_tick += size

    def consume_deficit(self) -> int:
        deficit = max(0, self.target_bytes_per_tick - self.bytes_sent_in_tick)
        self.bytes_sent_in_tick = 0
        return deficit
