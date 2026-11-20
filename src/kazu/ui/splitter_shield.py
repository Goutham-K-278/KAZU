"""Transparent pointer-event shield during splitter drags (Bug #3 fix).

Chromium's native surface can steal mouse-move events when a user drags a
QSplitter handle quickly. Raising a transparent overlay strictly while the
splitter handle is pressed restores butter-smooth 60 FPS resizing.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QSplitter, QWidget


class SplitterDragShield(QObject):
    """Installs an event filter on a QSplitter handle to guard active drags."""

    def __init__(self, host_widget: QWidget) -> None:
        super().__init__(host_widget)
        self._host = host_widget
        self._overlay = QWidget(host_widget)
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._overlay.setStyleSheet("background: transparent;")
        self._overlay.hide()

    def attach_to_splitter(self, splitter: QSplitter) -> None:
        """Guard every handle of `splitter`."""
        for idx in range(1, splitter.count()):
            handle = splitter.handle(idx)
            if handle is not None:
                handle.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            self._overlay.setGeometry(self._host.rect())
            self._overlay.raise_()
            self._overlay.show()
        elif etype == QEvent.Type.MouseButtonRelease:
            self._overlay.hide()
        return super().eventFilter(watched, event)
