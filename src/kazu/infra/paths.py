"""Owner-only OS directory management with path traversal protection."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME: str = "kazu"
OWNER_ONLY_DIR_MODE: int = 0o700
_SAFE_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _default_base_dirs() -> tuple[Path, Path, Path]:
    """Resolve OS-appropriate (data, cache, log) directories."""
    try:
        from platformdirs import user_cache_dir, user_data_dir, user_log_dir

        return (
            Path(user_data_dir(APP_DIR_NAME, appauthor=False)),
            Path(user_cache_dir(APP_DIR_NAME, appauthor=False)),
            Path(user_log_dir(APP_DIR_NAME, appauthor=False)),
        )
    except ImportError:
        home = Path.home()
        return (
            home / ".local" / "share" / APP_DIR_NAME,
            home / ".cache" / APP_DIR_NAME,
            home / ".local" / "state" / APP_DIR_NAME / "logs",
        )


def ensure_owner_only_dir(directory: Path) -> Path:
    """Create a directory and enforce owner-only permissions (0700 on POSIX)."""
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(directory, OWNER_ONLY_DIR_MODE)
    return directory


def validate_account_id(account_id: str) -> str:
    """Ensure account_id is safe for filesystem paths (blocks path traversal)."""
    if not _SAFE_ACCOUNT_ID_RE.match(account_id):
        raise ValueError(f"Unsafe account_id for filesystem path: {account_id!r}")
    return account_id


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Centralized, path-traversal-safe directory layout for Kazu."""

    data_dir: Path
    cache_dir: Path
    log_dir: Path

    @classmethod
    def default(cls) -> AppPaths:
        data_dir, cache_dir, log_dir = _default_base_dirs()
        return cls(data_dir=data_dir, cache_dir=cache_dir, log_dir=log_dir)

    def ensure_base_dirs(self) -> None:
        """Create root data, cache, and log directories with owner-only permissions."""
        ensure_owner_only_dir(self.data_dir)
        ensure_owner_only_dir(self.data_dir / "profiles")
        ensure_owner_only_dir(self.data_dir / "companion")
        ensure_owner_only_dir(self.cache_dir)
        ensure_owner_only_dir(self.cache_dir / "profiles")
        ensure_owner_only_dir(self.log_dir)

    @property
    def db_path(self) -> Path:
        ensure_owner_only_dir(self.data_dir)
        return self.data_dir / "app.db"

    @property
    def log_file(self) -> Path:
        ensure_owner_only_dir(self.log_dir)
        return self.log_dir / "kazu.log"

    def _safe_child(self, base: Path, account_id: str, leaf: str | None = None) -> Path:
        safe_id = validate_account_id(account_id)
        base_resolved = ensure_owner_only_dir(base).resolve()
        target = (base_resolved / safe_id)
        if leaf:
            target = target / leaf
        resolved = target.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise ValueError("Path traversal detected while resolving account directory")
        return ensure_owner_only_dir(resolved)

    def profile_storage(self, account_id: str) -> Path:
        """Return owner-only persistent storage dir for an embedded account."""
        return self._safe_child(self.data_dir / "profiles", account_id, "storage")

    def profile_cache(self, account_id: str) -> Path:
        """Return owner-only HTTP cache dir for an embedded account."""
        return self._safe_child(self.cache_dir / "profiles", account_id, "cache")

    def companion_profile(self, account_id: str) -> Path:
        """Return owner-only real-browser profile dir for a Companion account."""
        return self._safe_child(self.data_dir / "companion", account_id)

    def wipe_account_data(self, account_id: str) -> None:
        """Delete storage, cache, and companion directories for an account."""
        safe_id = validate_account_id(account_id)
        roots = (
            self.data_dir / "profiles" / safe_id,
            self.cache_dir / "profiles" / safe_id,
            self.data_dir / "companion" / safe_id,
        )
        for path in roots:
            if path.exists():
                shutil.rmtree(path, ignore_errors=False)

    def clear_account_cache(self, account_id: str) -> None:
        """Clear HTTP cache for an account while preserving login cookies."""
        safe_id = validate_account_id(account_id)
        cache_root = self.cache_dir / "profiles" / safe_id / "cache"
        if cache_root.exists():
            shutil.rmtree(cache_root, ignore_errors=False)
        ensure_owner_only_dir(cache_root)
