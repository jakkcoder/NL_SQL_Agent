"""``DEV_LOCAL_SQLITE_MIRROR`` routing for development."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import SecretStr

from app.core.config import AppConfig


def test_dev_local_mirror_enables_sqlite_catalog_url(tmp_path: Path) -> None:
    dbf = tmp_path / "mirror.sqlite"
    sqlite3.connect(str(dbf)).close()
    cfg = AppConfig(
        environment="local",
        dev_local_sqlite_mirror=str(dbf),
        dev_database_url=SecretStr("postgresql://user:pass@localhost:5432/warehouse"),
    )
    assert cfg.dev_local_sqlite_mirror_file_url is not None
    assert cfg.dev_local_sqlite_mirror_file_url.startswith("sqlite:///")
    assert cfg.filter_catalog_refresh_database_url == cfg.dev_local_sqlite_mirror_file_url


def test_dev_local_mirror_ignored_in_production(tmp_path: Path) -> None:
    dbf = tmp_path / "mirror.sqlite"
    sqlite3.connect(str(dbf)).close()
    cfg = AppConfig(
        environment="production",
        dev_local_sqlite_mirror=str(dbf),
        prod_database_url=SecretStr("postgresql://user:pass@prod-host:5432/warehouse"),
    )
    assert cfg.dev_local_sqlite_mirror_file_url is None
    assert "mirror" not in (cfg.filter_catalog_refresh_database_url or "")
