"""USE_LOCAL_DOCKER_POSTGRES routes the app to the local clone container."""

from __future__ import annotations

from pydantic import SecretStr

from app.core.config import AppConfig


def test_local_docker_url_used_in_development_by_default() -> None:
    cfg = AppConfig(
        environment="local",
        dev_database_url=SecretStr("postgresql://remote:pass@10.0.0.1:5406/warehouse"),
    )
    assert cfg.use_local_docker_postgres is True
    assert cfg.database_url_value == "postgresql://localdev:localdev@localhost:5433/investor_db_local"


def test_remote_dev_url_when_local_docker_disabled() -> None:
    remote = "postgresql://remote:pass@10.0.0.1:5406/warehouse"
    cfg = AppConfig(
        environment="local",
        use_local_docker_postgres=False,
        dev_database_url=SecretStr(remote),
    )
    assert cfg.database_url_value == remote


def test_local_docker_ignored_in_production() -> None:
    prod = "postgresql://prod:pass@prod-host:5432/warehouse"
    cfg = AppConfig(
        environment="production",
        use_local_docker_postgres=True,
        prod_database_url=SecretStr(prod),
    )
    assert cfg.database_url_value == prod
