"""Tests for investor schema contract helpers (no live DB required)."""

from pathlib import Path

from app.models.agent_state import STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT
from app.services.investor_schema_contract import (
    compact_schema_contract,
    packaged_schema_contract_path,
    schema_for_search_plan_llm,
)


def test_compact_schema_contract_strips_heavy_fields():
    full = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "tables": [
            {
                "schema": "public",
                "table": "investor",
                "fully_qualified": "public.investor",
                "is_partitioned_parent": False,
                "partition_key_def": None,
                "primary_key_columns": ["uuid"],
                "foreign_keys": [],
                "columns": [
                    {
                        "column_name": "uuid",
                        "ordinal_position": 1,
                        "data_type": "uuid",
                        "udt_name": "uuid",
                        "is_nullable": "NO",
                        "column_default": None,
                        "pg_comment": None,
                    }
                ],
            }
        ],
    }
    slim = compact_schema_contract(full)
    assert slim["contract_kind"] == "investor_schema_compact"
    assert slim["table_count"] == 1
    assert slim["column_count"] == 1
    col0 = slim["tables"][0]["columns"][0]
    assert col0["name"] == "uuid"
    assert "column_name" not in col0


def test_schema_for_search_plan_llm_prefers_session_over_packaged():
    fake_compact = {
        "contract_kind": "investor_schema_compact",
        "tables": [],
        "table_count": 0,
        "column_count": 0,
    }
    session = {STATE_KEY_INVESTOR_SCHEMA_CONTRACT_COMPACT: fake_compact}
    assert schema_for_search_plan_llm(session) is fake_compact


def test_packaged_schema_file_path_exists_in_repo():
    p = packaged_schema_contract_path()
    assert p.name == "investor_db_schema_contract.json"
    assert p.parent.name == "data"
    assert (Path(__file__).resolve().parents[1] / "app" / "data") == p.parent


def test_ensure_investor_schema_for_search_session_calls_live_once(monkeypatch):
    from app.models.agent_state import STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED
    from app.services import investor_schema_contract as isc

    calls = {"n": 0}

    def fake_build(_url):
        calls["n"] += 1
        return {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "tables_found": 1,
            "tables_missing_in_database": [],
            "tables": [
                {
                    "schema": "public",
                    "table": "investor",
                    "fully_qualified": "public.investor",
                    "is_partitioned_parent": False,
                    "partition_key_def": None,
                    "primary_key_columns": [],
                    "foreign_keys": [],
                    "column_count_information_schema": 1,
                    "column_count_pg_attribute_non_dropped": 1,
                    "columns": [
                        {
                            "column_name": "uuid",
                            "ordinal_position": 1,
                            "column_default": None,
                            "is_nullable": "NO",
                            "data_type": "uuid",
                            "udt_catalog": None,
                            "udt_schema": "pg_catalog",
                            "udt_name": "uuid",
                            "character_maximum_length": None,
                            "character_octet_length": None,
                            "numeric_precision": None,
                            "numeric_precision_radix": None,
                            "numeric_scale": None,
                            "datetime_precision": None,
                            "domain_catalog": None,
                            "domain_schema": None,
                            "domain_name": None,
                            "collation_catalog": None,
                            "collation_schema": None,
                            "collation_name": None,
                            "dtd_identifier": "1",
                            "identity_generation": None,
                            "identity_start": None,
                            "identity_increment": None,
                            "identity_maximum": None,
                            "identity_minimum": None,
                            "identity_cycle": "NO",
                            "is_generated": "NEVER",
                            "generation_expression": None,
                            "is_updatable": "YES",
                            "pg_comment": None,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(isc, "build_full_schema_contract", fake_build)
    monkeypatch.setattr(
        isc,
        "write_full_schema_contract_atomic",
        lambda full, path=None: isc.packaged_schema_contract_path(),
    )

    session: dict = {}
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    isc.ensure_investor_schema_for_search_session(session, "postgresql://stub")
    assert calls["n"] == 1
    assert session[STATE_KEY_INVESTOR_SCHEMA_SESSION_FETCHED] is True

    isc.ensure_investor_schema_for_search_session(session, "postgresql://stub")
    assert calls["n"] == 1
