"""Ordered teardown coordinator (Problem B3 fix).

Guarantees that embedded web views and pages are deleted and their deferred
deletes processed BEFORE profiles are destroyed and SQLite is checkpointed,
preventing lost cookies or profile corruption on quit.
"""

from __future__ import annotations

from collections.abc import Callable
import logging

logger = logging.getLogger("kazu.shutdown")


class ShutdownCoordinator:
    """Executes shutdown phases in strict deterministic order."""

    def __init__(self) -> None:
        self._hide_views: list[Callable[[], None]] = []
        self._destroy_views_and_pages: list[Callable[[], None]] = []
        self._process_events: Callable[[], None] | None = None
        self._destroy_profiles: list[Callable[[], None]] = []
        self._checkpoint_storage: list[Callable[[], None]] = []
        self._executed: bool = False

    def register_hide_views(self, callback: Callable[[], None]) -> None:
        self._hide_views.append(callback)

    def register_destroy_views_and_pages(self, callback: Callable[[], None]) -> None:
        self._destroy_views_and_pages.append(callback)

    def set_event_processor(self, callback: Callable[[], None]) -> None:
        self._process_events = callback

    def register_destroy_profiles(self, callback: Callable[[], None]) -> None:
        self._destroy_profiles.append(callback)

    def register_checkpoint_storage(self, callback: Callable[[], None]) -> None:
        self._checkpoint_storage.append(callback)

    def execute(self) -> None:
        """Run all teardown steps in strict order (idempotent)."""
        if self._executed:
            return
        self._executed = True

        self._run_phase("hide_views", self._hide_views)
        self._run_phase("destroy_views_and_pages", self._destroy_views_and_pages)

        if self._process_events is not None:
            try:
                self._process_events()
            except Exception as exc:
                logger.warning("Deferred delete processing failed: %s", exc)

        self._run_phase("destroy_profiles", self._destroy_profiles)
        self._run_phase("checkpoint_storage", self._checkpoint_storage)
        logger.info("Clean shutdown completed.")

    @staticmethod
    def _run_phase(phase_name: str, callbacks: list[Callable[[], None]]) -> None:
        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                logger.warning("Shutdown phase '%s' step failed: %s", phase_name, exc)
