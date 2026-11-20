"""Single-instance lock using Qt QLocalServer (Problem B3 fix).

Prevents two copies of Kazu from opening the same Chromium profile folders
simultaneously. A second launch signals the running instance to focus itself.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger("kazu.single_instance")

DEFAULT_SERVER_NAME: str = "kazu-desktop-workspace-v1"
CONNECT_TIMEOUT_MS: int = 300


class SingleInstanceLock:
    """Ensures only one Kazu process owns the local profiles at a time."""

    def __init__(self, server_name: str = DEFAULT_SERVER_NAME) -> None:
        self._server_name = server_name
        self._server: object | None = None
        self._on_activate: Callable[[], None] | None = None

    def try_acquire(self, on_activate: Callable[[], None] | None = None) -> bool:
        """Acquire the lock. Returns False if another instance is already running."""
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        self._on_activate = on_activate

        probe = QLocalSocket()
        probe.connectToServer(self._server_name)
        if probe.waitForConnected(CONNECT_TIMEOUT_MS):
            probe.write(b"FOCUS")
            probe.flush()
            probe.waitForBytesWritten(CONNECT_TIMEOUT_MS)
            probe.disconnectFromServer()
            logger.info("Existing Kazu instance detected; sent focus signal.")
            return False

        # Clean up stale socket left after a crash (e.g. kill -9).
        QLocalServer.removeServer(self._server_name)

        server = QLocalServer()
        if not server.listen(self._server_name):
            logger.warning("Could not listen on single-instance socket.")
            return False

        server.newConnection.connect(self._handle_new_connection)
        self._server = server
        return True

    def _handle_new_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()  # type: ignore[attr-defined]
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._consume_message(socket))

    def _consume_message(self, socket: object) -> None:
        data = bytes(socket.readAll())  # type: ignore[attr-defined]
        socket.disconnectFromServer()  # type: ignore[attr-defined]
        if b"FOCUS" in data and self._on_activate is not None:
            self._on_activate()

    def release(self) -> None:
        """Close the local server cleanly during shutdown."""
        if self._server is not None:
            self._server.close()  # type: ignore[attr-defined]
            self._server = None
