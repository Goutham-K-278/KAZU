"""Single-page 5-section Settings dialog (§8.10)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from kazu import __version__
from kazu.domain.models import AppSettings, DensityMode, ThemeMode, ZoomMode
from kazu.infra.memory import MemoryMonitor


class SettingsDialog(QDialog):
    """Clean one-page settings grouped into General, Appearance, Performance, Privacy, About."""

    def __init__(
        self,
        settings: AppSettings,
        memory_monitor: MemoryMonitor,
        on_freeze_other_spaces: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kazu Settings")
        self.setMinimumSize(540, 560)
        self._settings = settings

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setSpacing(12)

        # 1. General
        gen_box = QGroupBox("General")
        gen_form = QFormLayout(gen_box)
        self._restore_cb = QCheckBox("Restore last session on launch")
        self._restore_cb.setChecked(settings.restore_last_session)
        self._tray_cb = QCheckBox("Close to system tray")
        self._tray_cb.setChecked(settings.close_to_tray)
        self._confirm_delete_space_cb = QCheckBox("Ask for confirmation before deleting a Space")
        self._confirm_delete_space_cb.setChecked(settings.confirm_delete_space)
        gen_form.addRow(self._restore_cb)
        gen_form.addRow(self._tray_cb)
        gen_form.addRow(self._confirm_delete_space_cb)
        body.addWidget(gen_box)

        # 2. Appearance
        app_box = QGroupBox("Appearance")
        app_form = QFormLayout(app_box)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems([m.value for m in ThemeMode])
        self._theme_combo.setCurrentText(settings.theme.value)

        self._density_combo = QComboBox()
        self._density_combo.addItems([m.value for m in DensityMode])
        self._density_combo.setCurrentText(settings.density.value)

        self._zoom_combo = QComboBox()
        self._zoom_combo.addItems([m.value for m in ZoomMode])
        self._zoom_combo.setCurrentText(settings.zoom_mode.value)

        app_form.addRow("Theme:", self._theme_combo)
        app_form.addRow("Density:", self._density_combo)
        app_form.addRow("Narrow panes:", self._zoom_combo)
        body.addWidget(app_box)

        # 3. Performance & truthful recursive RAM diagnostics
        perf_box = QGroupBox("Performance & Diagnostics")
        perf_form = QFormLayout(perf_box)
        self._freeze_spin = QSpinBox()
        self._freeze_spin.setRange(1, 120)
        self._freeze_spin.setValue(settings.freeze_after_minutes)
        self._discard_spin = QSpinBox()
        self._discard_spin.setRange(5, 240)
        self._discard_spin.setValue(settings.discard_after_minutes)

        sample = memory_monitor.sample()
        ram_lbl = QLabel(
            f"{sample.total_rss_mb:.1f} MB total "
            f"(main {sample.main_rss_mb:.1f} MB + {sample.child_count} renderer processes)"
        )
        freeze_now_btn = QPushButton("Freeze other Spaces now")
        freeze_now_btn.clicked.connect(on_freeze_other_spaces)

        perf_form.addRow("Freeze hidden Spaces after (min):", self._freeze_spin)
        perf_form.addRow("Discard hidden Spaces after (min):", self._discard_spin)
        perf_form.addRow("Live recursive RAM:", ram_lbl)
        perf_form.addRow("", freeze_now_btn)
        body.addWidget(perf_box)

        # 4. Privacy & Shortcuts
        priv_box = QGroupBox("Privacy & Shortcuts")
        priv_form = QFormLayout(priv_box)
        self._passthrough_cb = QCheckBox(
            "Pass-Through Mode (send all keyboard shortcuts straight to websites)"
        )
        self._passthrough_cb.setChecked(settings.pass_through_mode)
        enc_tip = QLabel(
            "Tip: Sessions stay in owner-only local folders. Enable OS full-disk encryption "
            "(BitLocker / FileVault / LUKS) for maximum protection."
        )
        enc_tip.setObjectName("MutedLabel")
        enc_tip.setWordWrap(True)
        priv_form.addRow(self._passthrough_cb)
        priv_form.addRow(enc_tip)
        body.addWidget(priv_box)

        # 5. About
        about_box = QGroupBox("About")
        about_form = QFormLayout(about_box)
        about_form.addRow("Version:", QLabel(f"Kazu {__version__}"))
        about_form.addRow(
            "Trust guarantee:",
            QLabel("Zero credential handling. Zero scraping. Open source."),
        )
        body.addWidget(about_box)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        footer = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._save_and_accept)
        footer.addStretch(1)
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        outer.addLayout(footer)

    def _save_and_accept(self) -> None:
        self._settings.restore_last_session = self._restore_cb.isChecked()
        self._settings.close_to_tray = self._tray_cb.isChecked()
        self._settings.confirm_delete_space = self._confirm_delete_space_cb.isChecked()
        self._settings.theme = ThemeMode(self._theme_combo.currentText())
        self._settings.density = DensityMode(self._density_combo.currentText())
        self._settings.zoom_mode = ZoomMode(self._zoom_combo.currentText())
        self._settings.freeze_after_minutes = self._freeze_spin.value()
        self._settings.discard_after_minutes = max(
            self._freeze_spin.value() + 1,
            self._discard_spin.value(),
        )
        self._settings.pass_through_mode = self._passthrough_cb.isChecked()
        self.accept()
