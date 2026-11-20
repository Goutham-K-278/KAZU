"""Account management controller."""

from __future__ import annotations

from kazu.domain.layout import clear_account_references, deserialize_layout, serialize_layout
from kazu.domain.models import (
    ACCOUNT_COLOR_KEYS,
    Account,
    EngineKind,
    clamp_zoom,
    new_id,
    utc_now_iso,
)
from kazu.domain.providers import ProviderPresetRegistry
from kazu.infra.db import Database
from kazu.infra.paths import AppPaths


class AccountController:
    """Manages persistent account creation, updates, engine switching, and data wipe."""

    def __init__(
        self,
        db: Database,
        paths: AppPaths,
        presets: ProviderPresetRegistry,
    ) -> None:
        self._db = db
        self._paths = paths
        self._presets = presets

    def list_accounts(self) -> list[Account]:
        return self._db.list_accounts()

    def get_account(self, account_id: str) -> Account | None:
        return self._db.get_account(account_id)

    def create_account(
        self,
        provider_key: str,
        label: str | None = None,
        custom_url: str | None = None,
        engine: EngineKind | None = None,
    ) -> Account:
        """Create and persist a new isolated account with an auto-assigned color."""
        preset = self._presets.get(provider_key)
        existing = self._db.list_accounts()

        home_url = (custom_url or preset.url).strip()
        if not (home_url.startswith("https://") or home_url.startswith("http://")):
            raise ValueError("Account URL must start with https:// or http://")

        resolved_label = (label or self._next_default_label(preset.name, existing)).strip()
        resolved_engine = engine if engine is not None else preset.pane_type
        color = self._next_color(existing)

        account = Account(
            id=new_id(),
            label=resolved_label,
            provider_key=preset.key,
            home_url=home_url,
            engine=resolved_engine,
            color=color,
        )
        self._db.upsert_account(account)

        # Pre-create owner-only directories immediately.
        if account.engine == EngineKind.COMPANION:
            self._paths.companion_profile(account.id)
        else:
            self._paths.profile_storage(account.id)
            self._paths.profile_cache(account.id)

        return account

    def rename_account(self, account_id: str, new_label: str) -> Account | None:
        account = self._db.get_account(account_id)
        if account is None:
            return None
        cleaned = new_label.strip()
        if not cleaned:
            return account
        account.label = cleaned
        account.last_used_at = utc_now_iso()
        self._db.upsert_account(account)
        return account

    def set_color(self, account_id: str, color_key: str) -> Account | None:
        account = self._db.get_account(account_id)
        if account is None or color_key not in ACCOUNT_COLOR_KEYS:
            return account
        account.color = color_key
        self._db.upsert_account(account)
        return account

    def set_zoom(self, account_id: str, zoom: float) -> Account | None:
        account = self._db.get_account(account_id)
        if account is None:
            return None
        account.zoom = clamp_zoom(zoom)
        self._db.upsert_account(account)
        return account

    def set_keep_alive(self, account_id: str, keep_alive: bool) -> Account | None:
        account = self._db.get_account(account_id)
        if account is None:
            return None
        account.keep_alive = bool(keep_alive)
        self._db.upsert_account(account)
        return account

    def switch_engine(self, account_id: str, engine: EngineKind) -> Account | None:
        """Switch an account between embedded QtWebEngine and Companion Mode."""
        account = self._db.get_account(account_id)
        if account is None:
            return None
        account.engine = engine
        account.last_used_at = utc_now_iso()
        self._db.upsert_account(account)
        if engine == EngineKind.COMPANION:
            self._paths.companion_profile(account.id)
        else:
            self._paths.profile_storage(account.id)
            self._paths.profile_cache(account.id)
        return account

    def delete_and_wipe(self, account_id: str) -> bool:
        """Remove an account from DB, clear Space references, and wipe on-disk sessions."""
        account = self._db.get_account(account_id)
        if account is None:
            return False

        for space in self._db.list_spaces():
            tree = deserialize_layout(space.layout_json)
            if clear_account_references(tree, account_id) > 0:
                space.layout_json = serialize_layout(tree)
                self._db.upsert_space(space)

        self._db.delete_account(account_id)
        self._paths.wipe_account_data(account_id)
        return True

    @staticmethod
    def _next_color(existing: list[Account]) -> str:
        used_counts = {key: 0 for key in ACCOUNT_COLOR_KEYS}
        for acc in existing:
            if acc.color in used_counts:
                used_counts[acc.color] += 1
        return min(ACCOUNT_COLOR_KEYS, key=lambda key: used_counts[key])

    @staticmethod
    def _next_default_label(provider_name: str, existing: list[Account]) -> str:
        existing_labels = {acc.label.lower() for acc in existing}
        if provider_name.lower() not in existing_labels:
            return provider_name
        index = 2
        while f"{provider_name} {index}".lower() in existing_labels:
            index += 1
        return f"{provider_name} {index}"
