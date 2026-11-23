"""Embedded QtWebEngine backend — the ONLY module allowed to import QtWebEngine*.

Implements:
- Atomic profile creation via QWebEngineProfileBuilder (Qt 6.9+) with 6.8 fallback
- Pre-paint theme background matching (Bug #2: zero dark-mode white flash)
- NavigationPolicy routing (in-pane redirects/OAuth; external links to OS browser)
- Centered, screen-clamped OAuthPopup sharing the account's profile + BlockDetector
- Native WebAuthnDialog hook for FIDO2 keys (Problem A4)
- Crash recovery, loadFinished zoom re-apply hook, BlockDetector, and Activity Guard
- Zero QWebChannel exposure and disabled file-URL access
- Download interception via downloadRequested so files actually save to disk
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QSizePolicy

from kazu.controllers.lifecycle import LifecycleTier
from kazu.controllers.navigation import (
    BlockDetector,
    DownloadService,
    NavigationAction,
    NavigationPolicy,
)
from kazu.domain.models import Account
from kazu.domain.providers import ProviderPreset, ProviderPresetRegistry
from kazu.infra.paths import AppPaths
from kazu.ui.oauth_popup import OAuthPopup
from kazu.ui.webauthn_dialog import WebAuthnDialog

logger = logging.getLogger("kazu.engine_qt")

HTTP_CACHE_MAX_BYTES: int = 256 * 1024 * 1024  # 256 MB per account


def _build_persistent_profile(
    account_id: str,
    paths: AppPaths,
    parent: Any = None,
) -> QWebEngineProfile:
    """Create an isolated persistent profile atomically via QWebEngineProfileBuilder."""
    storage_path = str(paths.profile_storage(account_id))
    cache_path = str(paths.profile_cache(account_id))

    try:
        from PySide6.QtWebEngineCore import QWebEngineProfileBuilder

        builder = QWebEngineProfileBuilder()
        builder.setPersistentStoragePath(storage_path)
        builder.setCachePath(cache_path)
        builder.setHttpCacheMaximumSize(HTTP_CACHE_MAX_BYTES)
        builder.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        if hasattr(builder, "setPersistentPermissionsPolicy"):
            builder.setPersistentPermissionsPolicy(
                QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk
            )
        profile = builder.createProfile(account_id, parent)
    except (ImportError, AttributeError):
        profile = QWebEngineProfile(account_id, parent)
        profile.setPersistentStoragePath(storage_path)
        profile.setCachePath(cache_path)
        profile.setHttpCacheMaximumSize(HTTP_CACHE_MAX_BYTES)
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

    profile.setSpellCheckEnabled(True)
    # Keep Qt's default User-Agent; never impersonate another browser.
    return profile


class AgentPage(QWebEnginePage):
    """Single policy point for navigation, OAuth popups, WebAuthn, and hardening."""

    def __init__(
        self,
        profile: QWebEngineProfile,
        account: Account,
        preset: ProviderPreset,
        nav_policy: NavigationPolicy,
        block_detector: BlockDetector,
        bg_hex: str,
        on_google_blocked: Callable[[], None] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(profile, parent)
        self._account = account
        self._preset = preset
        self._nav_policy = nav_policy
        self._block_detector = block_detector
        self._on_google_blocked = on_google_blocked
        self._popups: list[tuple[OAuthPopup, QWebEngineView, QWebEnginePage]] = []

        # Bug #2: paint theme background before first load to prevent white flash.
        self.setBackgroundColor(QColor(bg_hex))

        # Harden page settings: no local file access, no QWebChannel bridge.
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)

        if hasattr(self, "webAuthUxRequested"):
            self.webAuthUxRequested.connect(self._handle_webauthn_request)

        if hasattr(self, "featurePermissionRequested"):
            self.featurePermissionRequested.connect(self._handle_feature_permission)

    def acceptNavigationRequest(
        self,
        url: QUrl | str,
        nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if not is_main_frame:
            return True

        qurl = url if isinstance(url, QUrl) else QUrl(url)
        url_str = qurl.toString()
        scheme = qurl.scheme().lower()

        if url_str.strip().lower() == "about:blank" or scheme == "blob":
            return True

        if scheme not in ("https", "http"):
            return False

        is_link_click = nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked

        decision = self._nav_policy.decide(
            url=url_str,
            preset=self._preset,
            home_url=self._account.home_url,
            is_user_link_click=is_link_click,
        )
        if decision == NavigationAction.ALLOW_IN_PANE:
            return True
        if decision == NavigationAction.OPEN_EXTERNAL:
            QDesktopServices.openUrl(qurl)
            return False
        return False

    def createWindow(self, win_type: QWebEnginePage.WebWindowType) -> QWebEnginePage:
        """Spawn a screen-clamped OAuthPopup sharing the same profile (Bug #10)."""
        popup_view = QWebEngineView()
        popup_page = QWebEnginePage(self.profile(), popup_view)
        popup_view.setPage(popup_page)

        dialog = OAuthPopup(web_view=popup_view, parent=self.parent())  # type: ignore[arg-type]

        def _check_popup_block(qurl: QUrl, title: str) -> None:
            if self._block_detector.is_google_blocked(qurl.toString(), title):
                dialog.close()
                if self._on_google_blocked is not None:
                    self._on_google_blocked()

        def _on_url_changed(qurl: QUrl) -> None:
            dialog.set_display_url(qurl.toString())
            _check_popup_block(qurl, popup_page.title())

        def _on_title_changed(title: str) -> None:
            _check_popup_block(popup_page.url(), title)

        popup_page.urlChanged.connect(_on_url_changed)
        popup_page.titleChanged.connect(_on_title_changed)
        popup_page.windowCloseRequested.connect(dialog.close)

        entry = (dialog, popup_view, popup_page)
        dialog.finished.connect(lambda _: self._cleanup_popup(entry))

        self._popups.append(entry)
        dialog.show()
        return popup_page

    def _cleanup_popup(
        self,
        entry: tuple[OAuthPopup, QWebEngineView, QWebEnginePage],
    ) -> None:
        dialog, popup_view, popup_page = entry
        if entry in self._popups:
            self._popups.remove(entry)
        popup_view.setPage(None)  # type: ignore[arg-type]
        popup_page.deleteLater()
        popup_view.deleteLater()
        dialog.deleteLater()

    def dispose_popups(self) -> None:
        """Close and detach any lingering OAuth popups before profile teardown."""
        for entry in list(self._popups):
            entry[0].close()
            self._cleanup_popup(entry)

    def _handle_webauthn_request(self, request: Any) -> None:
        dialog = WebAuthnDialog(request=request, parent=self.parent())  # type: ignore[arg-type]
        dialog.exec()

    def _handle_feature_permission(self, origin: QUrl, feature: Any) -> None:
        policy = QWebEnginePage.PermissionPolicy
        allowed_features = {
            getattr(QWebEnginePage.Feature, name, None)
            for name in (
                "Notifications",
                "MediaAudioCapture",
                "MediaVideoCapture",
                "MediaAudioVideoCapture",
            )
        }
        decision = (
            policy.PermissionGrantedByUser
            if feature in allowed_features
            else policy.PermissionDeniedByUser
        )
        self.setFeaturePermission(origin, feature, decision)  # type: ignore[arg-type]


class QtWebEnginePane:
    """Concrete PaneEngine backed by QWebEngineView + AgentPage."""

    def __init__(
        self,
        account: Account,
        profile: QWebEngineProfile,
        preset: ProviderPreset,
        nav_policy: NavigationPolicy,
        block_detector: BlockDetector,
        bg_hex: str,
        on_activity: Callable[[], None] | None = None,
        on_google_blocked: Callable[[], None] | None = None,
        on_crashed: Callable[[], None] | None = None,
        on_signed_out_changed: Callable[[bool], None] | None = None,
        on_load_finished: Callable[[bool], None] | None = None,
    ) -> None:
        self._account = account
        self._preset = preset
        self._block_detector = block_detector
        self._on_activity = on_activity
        self._on_google_blocked = on_google_blocked
        self._on_crashed = on_crashed
        self._on_signed_out_changed = on_signed_out_changed
        self._on_load_finished = on_load_finished
        self._disposed: bool = False

        self._view = QWebEngineView()
        self._view.setMinimumSize(0, 0)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._page = AgentPage(
            profile=profile,
            account=account,
            preset=preset,
            nav_policy=nav_policy,
            block_detector=block_detector,
            bg_hex=bg_hex,
            on_google_blocked=on_google_blocked,
            parent=self._view,
        )
        self._view.setPage(self._page)
        self._view.setZoomFactor(account.zoom)

        self._page.titleChanged.connect(self._handle_title_changed)
        self._page.urlChanged.connect(self._handle_url_changed)
        self._page.loadFinished.connect(self._handle_load_finished)
        self._page.recentlyAudibleChanged.connect(lambda _: self._emit_activity())
        self._page.renderProcessTerminated.connect(self._handle_crash)

    @property
    def widget(self) -> QWebEngineView:
        return self._view

    def load_url(self, url: str) -> None:
        if not self._disposed:
            self._view.load(QUrl(url))

    def reload(self) -> None:
        if not self._disposed:
            self._view.reload()

    def back(self) -> None:
        if not self._disposed:
            self._view.back()

    def forward(self) -> None:
        if not self._disposed:
            self._view.forward()

    def set_zoom(self, factor: float) -> None:
        if not self._disposed:
            self._view.setZoomFactor(factor)

    def find_text(self, query: str) -> None:
        if not self._disposed:
            self._view.findText(query)

    def set_lifecycle_tier(self, tier: LifecycleTier) -> None:
        if self._disposed:
            return
        state_enum = QWebEnginePage.LifecycleState
        if tier in (LifecycleTier.LIVE, LifecycleTier.HIDDEN_ACTIVE):
            self._page.setLifecycleState(state_enum.Active)
        elif tier == LifecycleTier.FROZEN:
            if self._page.lifecycleState() != state_enum.Discarded:
                self._page.setLifecycleState(state_enum.Frozen)
        elif tier == LifecycleTier.DISCARDED:
            self._page.setLifecycleState(state_enum.Discarded)

    def grab_snapshot_png(self) -> bytes:
        if self._disposed:
            return b""
        pixmap = self._view.grab()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        return bytes(buf.data())  # type: ignore[arg-type]

    def focus_view(self) -> bool:
        if self._disposed:
            return False
        self._view.setFocus()
        return self._view.hasFocus()

    def trigger_paste(self) -> None:
        if not self._disposed:
            self._page.triggerAction(QWebEnginePage.WebAction.Paste)

    def selected_text(self) -> str:
        if self._disposed:
            return ""
        return self._page.selectedText()

    def dispose(self) -> None:
        """Destroy popups, view, and page cleanly BEFORE profile teardown (idempotent)."""
        if self._disposed:
            return
        self._disposed = True
        self._page.dispose_popups()
        self._view.hide()
        self._view.setPage(None)  # type: ignore[arg-type]
        self._page.deleteLater()
        self._view.deleteLater()

    def _emit_activity(self) -> None:
        if not self._disposed and self._on_activity is not None:
            self._on_activity()

    def _handle_load_finished(self, ok: bool) -> None:
        if not self._disposed and self._on_load_finished is not None:
            self._on_load_finished(ok)

    def _handle_title_changed(self, title: str) -> None:
        if self._disposed:
            return
        self._emit_activity()
        current_url = self._page.url().toString()
        if (
            self._block_detector.is_google_blocked(current_url, title)
            and self._on_google_blocked is not None
        ):
            self._on_google_blocked()

    def _handle_url_changed(self, qurl: QUrl) -> None:
        if self._disposed:
            return
        url_str = qurl.toString()
        if (
            self._block_detector.is_google_blocked(url_str, self._page.title())
            and self._on_google_blocked is not None
        ):
            self._on_google_blocked()
        if self._on_signed_out_changed is not None:
            self._on_signed_out_changed(
                self._block_detector.is_signed_out_url(url_str, self._preset)
            )

    def _handle_crash(self, _status: Any, _exit_code: int) -> None:
        logger.warning("Embedded renderer terminated for account %s", self._account.id)
        if not self._disposed and self._on_crashed is not None:
            self._on_crashed()


class QtWebEngineFactory:
    """App-owned profile registry guaranteeing profiles outlive every page (Rule 7.1)."""

    def __init__(
        self,
        paths: AppPaths,
        bg_hex: str = "#0F0F10",
        presets: ProviderPresetRegistry | None = None,
        download_dir: str = "",
        on_download_started: Callable[[str, str], None] | None = None,
    ) -> None:
        self._paths = paths
        self._bg_hex = bg_hex
        self._presets = presets or ProviderPresetRegistry()
        self._nav_policy = NavigationPolicy()
        self._block_detector = BlockDetector()
        self._profiles: dict[str, QWebEngineProfile] = {}
        self._download_service = DownloadService()
        self._download_dir = download_dir
        self._on_download_started = on_download_started

    def set_background_hex(self, bg_hex: str) -> None:
        self._bg_hex = bg_hex

    def set_download_dir(self, download_dir: str) -> None:
        self._download_dir = download_dir

    def get_or_create_profile(self, account_id: str) -> QWebEngineProfile:
        profile = self._profiles.get(account_id)
        if profile is None:
            profile = _build_persistent_profile(account_id, self._paths)
            profile.downloadRequested.connect(self._handle_download)
            self._profiles[account_id] = profile
        return profile

    def _handle_download(self, download: QWebEngineDownloadRequest) -> None:
        suggested = download.suggestedFileName() or "download"
        target_dir = (
            Path(self._download_dir).expanduser()
            if self._download_dir
            else Path.home() / "Downloads"
        )

        try:
            dest = self._download_service.resolve_unique_path(target_dir, suggested)
        except (ValueError, OSError):
            logger.warning("Download path resolution failed for %r; using fallback.", suggested)
            dest = target_dir / Path(suggested).name

        download.setDownloadDirectory(str(dest.parent))
        download.setDownloadFileName(dest.name)
        download.accept()

        logger.info("Download accepted: %s", dest.name)
        if self._on_download_started is not None:
            self._on_download_started(dest.name, str(dest.parent))

    def create_pane(
        self,
        account: Account,
        *,
        on_activity: Callable[[], None] | None = None,
        on_google_blocked: Callable[[], None] | None = None,
        on_crashed: Callable[[], None] | None = None,
        on_signed_out_changed: Callable[[bool], None] | None = None,
        on_load_finished: Callable[[bool], None] | None = None,
    ) -> QtWebEnginePane:
        profile = self.get_or_create_profile(account.id)
        preset = self._presets.get(account.provider_key)
        return QtWebEnginePane(
            account=account,
            profile=profile,
            preset=preset,
            nav_policy=self._nav_policy,
            block_detector=self._block_detector,
            bg_hex=self._bg_hex,
            on_activity=on_activity,
            on_google_blocked=on_google_blocked,
            on_crashed=on_crashed,
            on_signed_out_changed=on_signed_out_changed,
            on_load_finished=on_load_finished,
        )

    def dispose_all_profiles(self) -> None:
        """Destroy all profiles AFTER all views/pages have been deleted."""
        for profile in self._profiles.values():
            profile.deleteLater()
        self._profiles.clear()
