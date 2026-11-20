"""Recursive process-tree RAM monitor (Bug #7 fix).

Measures RSS across the Python process AND all child QtWebEngineProcess
renderers so memory diagnostics and soft RAM warnings report the truth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

BYTES_PER_MB: float = 1024.0 * 1024.0
DEFAULT_SOFT_WARNING_MB: float = 2048.0


@dataclass(frozen=True, slots=True)
class MemorySample:
    """Snapshot of total process-tree RSS memory usage."""

    total_rss_bytes: int
    main_rss_bytes: int
    child_count: int
    system_available_bytes: int | None

    @property
    def total_rss_mb(self) -> float:
        return round(self.total_rss_bytes / BYTES_PER_MB, 1)

    @property
    def main_rss_mb(self) -> float:
        return round(self.main_rss_bytes / BYTES_PER_MB, 1)


class MemoryMonitor:
    """Computes recursive RSS across the app and all child browser renderers."""

    def __init__(self, soft_warning_mb: float = DEFAULT_SOFT_WARNING_MB) -> None:
        self._soft_warning_mb = max(256.0, float(soft_warning_mb))

    def sample(self, pid: int | None = None) -> MemorySample:
        """Return recursive RSS for `pid` (defaults to current process)."""
        target_pid = pid if pid is not None else os.getpid()
        try:
            import psutil
        except ImportError:
            return self._fallback_sample()

        try:
            proc = psutil.Process(target_pid)
            main_rss = int(proc.memory_info().rss)
            total_rss = main_rss
            children = proc.children(recursive=True)
            for child in children:
                try:
                    total_rss += int(child.memory_info().rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            available = int(psutil.virtual_memory().available)
            return MemorySample(
                total_rss_bytes=total_rss,
                main_rss_bytes=main_rss,
                child_count=len(children),
                system_available_bytes=available,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return MemorySample(0, 0, 0, None)

    def should_warn(self, sample: MemorySample) -> bool:
        """Return True when recursive memory exceeds the soft warning threshold."""
        return sample.total_rss_mb >= self._soft_warning_mb

    @staticmethod
    def _fallback_sample() -> MemorySample:
        """Fallback when psutil is unavailable (e.g. minimal headless test env)."""
        try:
            import resource

            ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # type: ignore[attr-defined]
            # Linux reports KB; macOS reports bytes.
            rss_bytes = ru_maxrss * 1024 if os.uname().sysname == "Linux" else ru_maxrss  # type: ignore[attr-defined]
            return MemorySample(rss_bytes, rss_bytes, 0, None)
        except (ImportError, AttributeError):
            return MemorySample(0, 0, 0, None)
