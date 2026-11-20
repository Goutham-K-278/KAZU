"""SQLite persistence with PRAGMA user_version ordered migrations.

All queries use parameterized bindings. UI widgets never access this module
directly — controllers mediate all reads and writes.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from kazu.domain.models import (
    Account,
    AppSettings,
    DensityMode,
    EngineKind,
    Space,
    ThemeMode,
    ZoomMode,
)

CURRENT_SCHEMA_VERSION: int = 1


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Initial schema: accounts, spaces, and key-value settings."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            provider_key TEXT NOT NULL,
            home_url TEXT NOT NULL,
            engine TEXT NOT NULL DEFAULT 'embedded',
            color TEXT NOT NULL,
            zoom REAL NOT NULL DEFAULT 1.0,
            keep_alive INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            layout_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


MIGRATIONS: tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...] = (
    (1, _migrate_v1),
)


class Database:
    """Thread-safe-by-convention SQLite repository for Kazu."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._run_migrations()

    def _run_migrations(self) -> None:
        current = int(self._conn.execute("PRAGMA user_version;").fetchone()[0])
        for target_version, migrate_fn in MIGRATIONS:
            if current < target_version:
                with self._conn:
                    migrate_fn(self._conn)
                    self._conn.execute(f"PRAGMA user_version = {int(target_version)};")
                current = target_version

    @property
    def schema_version(self) -> int:
        return int(self._conn.execute("PRAGMA user_version;").fetchone()[0])

    # --- Accounts ---

    def list_accounts(self) -> list[Account]:
        rows = self._conn.execute(
            """
            SELECT id, label, provider_key, home_url, engine, color, zoom,
                   keep_alive, created_at, last_used_at
            FROM accounts
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [self._row_to_account(row) for row in rows]

    def get_account(self, account_id: str) -> Account | None:
        row = self._conn.execute(
            """
            SELECT id, label, provider_key, home_url, engine, color, zoom,
                   keep_alive, created_at, last_used_at
            FROM accounts
            WHERE id = ?
            """,
            (account_id,),
        ).fetchone()
        return self._row_to_account(row) if row is not None else None

    def upsert_account(self, account: Account) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO accounts (
                    id, label, provider_key, home_url, engine, color, zoom,
                    keep_alive, created_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label = excluded.label,
                    provider_key = excluded.provider_key,
                    home_url = excluded.home_url,
                    engine = excluded.engine,
                    color = excluded.color,
                    zoom = excluded.zoom,
                    keep_alive = excluded.keep_alive,
                    last_used_at = excluded.last_used_at
                """,
                (
                    account.id,
                    account.label,
                    account.provider_key,
                    account.home_url,
                    account.engine.value,
                    account.color,
                    account.zoom,
                    int(account.keep_alive),
                    account.created_at,
                    account.last_used_at,
                ),
            )

    def delete_account(self, account_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    # --- Spaces ---

    def list_spaces(self) -> list[Space]:
        rows = self._conn.execute(
            """
            SELECT id, name, order_index, layout_json
            FROM spaces
            ORDER BY order_index ASC
            """
        ).fetchall()
        return [self._row_to_space(row) for row in rows]

    def get_space(self, space_id: str) -> Space | None:
        row = self._conn.execute(
            "SELECT id, name, order_index, layout_json FROM spaces WHERE id = ?",
            (space_id,),
        ).fetchone()
        return self._row_to_space(row) if row is not None else None

    def upsert_space(self, space: Space) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO spaces (id, name, order_index, layout_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    order_index = excluded.order_index,
                    layout_json = excluded.layout_json
                """,
                (space.id, space.name, space.order_index, space.layout_json),
            )

    def delete_space(self, space_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM spaces WHERE id = ?", (space_id,))

    def reorder_spaces(self, ordered_ids: list[str]) -> None:
        with self._conn:
            for index, space_id in enumerate(ordered_ids):
                self._conn.execute(
                    "UPDATE spaces SET order_index = ? WHERE id = ?",
                    (index, space_id),
                )

    # --- Settings ---

    def load_settings(self) -> AppSettings:
        rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        raw: dict[str, Any] = {}
        for row in rows:
            try:
                raw[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                raw[row["key"]] = row["value"]

        defaults = AppSettings()
        return AppSettings(
            restore_last_session=bool(raw.get("restore_last_session", defaults.restore_last_session)),  # noqa: E501
            launch_on_login=bool(raw.get("launch_on_login", defaults.launch_on_login)),
            close_to_tray=bool(raw.get("close_to_tray", defaults.close_to_tray)),
            confirm_delete_space=bool(raw.get("confirm_delete_space", defaults.confirm_delete_space)),  # noqa: E501
            theme=_safe_enum(ThemeMode, raw.get("theme"), defaults.theme),
            density=_safe_enum(DensityMode, raw.get("density"), defaults.density),
            accent_color=str(raw.get("accent_color", defaults.accent_color)),
            zoom_mode=_safe_enum(ZoomMode, raw.get("zoom_mode"), defaults.zoom_mode),
            freeze_after_minutes=int(raw.get("freeze_after_minutes", defaults.freeze_after_minutes)),  # noqa: E501
            discard_after_minutes=int(raw.get("discard_after_minutes", defaults.discard_after_minutes)),  # noqa: E501
            show_memory_per_pane=bool(raw.get("show_memory_per_pane", defaults.show_memory_per_pane)),  # noqa: E501
            pass_through_mode=bool(raw.get("pass_through_mode", defaults.pass_through_mode)),
            onboarding_completed=bool(raw.get("onboarding_completed", defaults.onboarding_completed)),  # noqa: E501
            sync_folder=str(raw.get("sync_folder", defaults.sync_folder)),
            download_dir=str(raw.get("download_dir", defaults.download_dir)),
            last_space_id=str(raw.get("last_space_id", defaults.last_space_id)),
        )

    def save_settings(self, settings: AppSettings) -> None:
        data = asdict(settings)
        with self._conn:
            for key, value in data.items():
                encoded = json.dumps(value.value if hasattr(value, "value") else value)
                self._conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, encoded),
                )

    def checkpoint(self) -> None:
        """Flush WAL journal to main database file before clean shutdown."""
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def close(self) -> None:
        """Checkpoint and close the SQLite connection cleanly."""
        try:
            self.checkpoint()
        finally:
            self._conn.close()

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            label=row["label"],
            provider_key=row["provider_key"],
            home_url=row["home_url"],
            engine=EngineKind(row["engine"]),
            color=row["color"],
            zoom=float(row["zoom"]),
            keep_alive=bool(row["keep_alive"]),
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
        )

    @staticmethod
    def _row_to_space(row: sqlite3.Row) -> Space:
        return Space(
            id=row["id"],
            name=row["name"],
            order_index=int(row["order_index"]),
            layout_json=row["layout_json"],
        )


def _safe_enum(enum_cls: type[Any], value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default
