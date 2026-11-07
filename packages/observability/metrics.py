"""In-process counters. These measure this process; they are not a telemetry product."""

from __future__ import annotations

from threading import Lock


class Counter:
    def __init__(self) -> None:
        self._values: dict[str, int] = {}
        self._lock = Lock()

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._values[name] = self._values.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


metrics = Counter()
