"""Embedded QtWebEngine backend — the ONLY module allowed to import QtWebEngine*.

Implements:
- Atomic profile creation via QWebEngineProfileBuilder (Qt 6.9+) with 6.8 fallback
- Pre-paint theme background matching (Bug #2: zero dark-mode white flash)
- NavigationPolicy routing (in-pane vs. system browser)
- Centered 520x680 OAuthPopup sharing the account's profile (Bug #10)
- Native WebAuthnDialog hook for FIDO2 keys (Problem A4)
- Crash recovery, BlockDetector, and Activity Guard signals
- Zero QWebChannel exposure and disabled file-URL access
- Download interception via downloadRequested so files actually save to disk
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QBuffer, QIODevice, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

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
        # Clean fallback for Qt 6.7/6.8 before QWebEngineProfileBuilder existed.
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
        bg_hex: str,
        parent: Any = None,
    ) -> None:
        super().__init__(profile, parent)
        self._account = account
        self._preset = preset
        self._nav_policy = nav_policy
        self._popups: list[OAuthPopup] = []

        # Bug #2: paint theme background before first load to prevent white flash.
        self.setBackgroundColor(QColor(bg_hex))

        # Harden page settings: no local file access, no QWebChannel bridge.
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)  # noqa: E501
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)

        # Problem A4: native FIDO2 / WebAuthn dialog.
        if hasattr(self, "webAuthUxRequested"):
            self.webAuthUxRequested.connect(self._handle_webauthn_request)

    def acceptNavigationRequest(
        self,
        url: QUrl,
        nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        # Always allow sub-frame navigations (ads, iframes, etc.).
        if not is_main_frame:
            return True

        scheme = url.scheme().lower()

        # Allow blob: URLs — Claude and other sites use these for file downloads.
        # Qt intercepts blob: navigations that have a Content-Disposition and fires
        # downloadRequested on the profile; blocking them here prevents that signal.
        if scheme == "blob":
            return True

        # Block everything that is not http/https (data:, javascript:, file:, etc.).
        if scheme not in ("https", "http"):
            return False

        decision = self._nav_policy.decide(
            url=url.toString(),
            preset=self._preset,
            home_url=self._account.home_url,
        )
        if decision == NavigationAction.ALLOW_IN_PANE:
            return True
        if decision == NavigationAction.OPEN_EXTERNAL:
            QDesktopServices.openUrl(url)
            return False
        return False

    def createWindow(self, win_type: QWebEnginePage.WebWindowType) -> QWebEnginePage:
        """Spawn a centered 520x680 OAuthPopup sharing the same profile (Bug #10)."""
        popup_view = QWebEngineView()
        popup_page = QWebEnginePage(self.profile(), popup_view)
        popup_view.setPage(popup_page)

        dialog = OAuthPopup(web_view=popup_view, parent=self.parent())

        # Track whether this popup visited an auth/OAuth domain so we know
        # whether to reload the main pane when it closes.
        visited_auth_domain: list[bool] = [False]

        def _on_url_changed(qurl: QUrl) -> None:
            dialog.set_display_url(qurl.toString())
            host = (qurl.host() or "").lower()
            from kazu.controllers.navigation import OAUTH_PASSTHROUGH_DOMAINS
            for auth_domain in OAUTH_PASSTHROUGH_DOMAINS:
                if host == auth_domain or host.endswith(f".{auth_domain}"):
                    visited_auth_domain[0] = True
                    return

        popup_page.urlChanged.connect(_on_url_changed)
        popup_page.windowCloseRequested.connect(dialog.close)
        dialog.finished.connect(lambda _: self._cleanup_popup(dialog, visited_auth_domain))

        self._popups.append(dialog)
        dialog.show()
        return popup_page

    def _cleanup_popup(self, dialog: OAuthPopup, visited_auth: list[bool] | None = None) -> None:
        if dialog in self._popups:
            self._popups.remove(dialog)
        did_oauth = visited_auth is not None and visited_auth[0]
        dialog.deleteLater()
        if did_oauth:
            # Navigate to the account's home URL (not a raw reload) so a stale
            # OAuth callback URL in the pane cannot trigger another Google auth
            # round-trip, which would cause a 400 Bad Request.
            # The session cookie is already written to the shared profile, so
            # loading home URL will give the app a fresh, authenticated page load.
            home = QUrl(self._account.home_url)
            QTimer.singleShot(500, lambda: self.setUrl(home))

    def _handle_webauthn_request(self, request: Any) -> None:
        dialog = WebAuthnDialog(request=request, parent=self.parent())
        dialog.exec()


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
    ) -> None:
        self._account = account
        self._preset = preset
        self._block_detector = block_detector
        self._on_activity = on_activity
        self._on_google_blocked = on_google_blocked
        self._on_crashed = on_crashed
        self._on_signed_out_changed = on_signed_out_changed

        self._view = QWebEngineView()
        self._page = AgentPage(
            profile=profile,
            account=account,
            preset=preset,
            nav_policy=nav_policy,
            bg_hex=bg_hex,
            parent=self._view,
        )
        self._view.setPage(self._page)
        self._view.setZoomFactor(account.zoom)

        self._page.titleChanged.connect(self._handle_title_changed)
        self._page.urlChanged.connect(self._handle_url_changed)
        self._page.recentlyAudibleChanged.connect(lambda _: self._emit_activity())
        self._page.renderProcessTerminated.connect(self._handle_crash)

    @property
    def widget(self) -> QWebEngineView:
        return self._view

    def load_url(self, url: str) -> None:
        self._view.load(QUrl(url))

    def reload(self) -> None:
        self._view.reload()

    def back(self) -> None:
        self._view.back()

    def forward(self) -> None:
        self._view.forward()

    def set_zoom(self, factor: float) -> None:
        self._view.setZoomFactor(factor)

    def find_text(self, query: str) -> None:
        self._view.findText(query)

    def set_lifecycle_tier(self, tier: LifecycleTier) -> None:
        """Map Kazu's 4-tier lifecycle onto QtWebEnginePage.LifecycleState."""
        state_enum = QWebEnginePage.LifecycleState
        if tier in (LifecycleTier.LIVE, LifecycleTier.HIDDEN_ACTIVE):
            self._page.setLifecycleState(state_enum.Active)
        elif tier == LifecycleTier.FROZEN:
            if self._page.lifecycleState() != state_enum.Discarded:
                self._page.setLifecycleState(state_enum.Frozen)
        elif tier == LifecycleTier.DISCARDED:
            self._page.setLifecycleState(state_enum.Discarded)

    def grab_snapshot_png(self) -> bytes:
        """Capture a lightweight PNG screenshot before discarding."""
        pixmap = self._view.grab()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        return bytes(buf.data())

    def focus_view(self) -> bool:
        self._view.setFocus()
        return self._view.hasFocus()

    def trigger_paste(self) -> None:
        self._page.triggerAction(QWebEnginePage.WebAction.Paste)

    def selected_text(self) -> str:
        return self._page.selectedText()

    def dispose(self) -> None:
        """Destroy view and page cleanly BEFORE profile teardown (Problem B3)."""
        self._view.hide()
        self._view.setPage(None)  # type: ignore[arg-type]
        self._page.deleteLater()
        self._view.deleteLater()

    def _emit_activity(self) -> None:
        if self._on_activity is not None:
            self._on_activity()

    def _handle_title_changed(self, title: str) -> None:
        self._emit_activity()
        current_url = self._page.url().toString()
        if self._block_detector.is_google_blocked(current_url, title) and self._on_google_blocked is not None:  # noqa: E501
            self._on_google_blocked()

    def _handle_url_changed(self, qurl: QUrl) -> None:
        url_str = qurl.toString()
        if self._block_detector.is_google_blocked(url_str, self._page.title()) and self._on_google_blocked is not None:  # noqa: E501
            self._on_google_blocked()
        if self._on_signed_out_changed is not None:
            self._on_signed_out_changed(
                self._block_detector.is_signed_out_url(url_str, self._preset)
            )

    def _handle_crash(self, _status: Any, _exit_code: int) -> None:
        logger.warning("Embedded renderer terminated for account %s", self._account.id)
        if self._on_crashed is not None:
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
            # Wire download interception once per profile.
            profile.downloadRequested.connect(self._handle_download)
            self._profiles[account_id] = profile
        return profile

    def _handle_download(self, download: QWebEngineDownloadRequest) -> None:
        """Accept a download, place it in the configured download dir, and notify the UI."""
        suggested = download.suggestedFileName() or "download"

        # Resolve the target directory: user-configured > OS Downloads folder.
        if self._download_dir:
            target_dir = Path(self._download_dir).expanduser()
        else:
            target_dir = Path.home() / "Downloads"

        try:
            dest = self._download_service.resolve_unique_path(target_dir, suggested)
        except (ValueError, OSError):
            logger.warning("Download path resolution failed for %r; using fallback.", suggested)
            dest = target_dir / suggested

        download.setDownloadDirectory(str(dest.parent))
        download.setDownloadFileName(dest.name)
        download.accept()

        logger.info("Download accepted: %s", dest)
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
        )

    def dispose_all_profiles(self) -> None:
        """Destroy all profiles AFTER all views/pages have been deleted."""
        for profile in self._profiles.values():
            profile.deleteLater()
        self._profiles.clear()
