import json
from pathlib import Path

import pytest

from app.services.filter_catalog import (
    FilterCatalog,
    _contract_catalog,
    _merge_db_values,
    load_catalog_from_file,
    refresh_catalog_from_db,
)


def test_contract_catalog_has_core_filters():
    data = _contract_catalog()
    filters = data["filters"]
    assert "eligibility" in filters
    assert set(filters["eligibility"]["values"]) == {"ALL", "YES", "NO"}
    assert "systematic_plans" in filters
    assert "SIP" in filters["systematic_plans"]["values"]


def test_merge_db_values_prepends_all_for_scheme_codes():
    catalog = _contract_catalog()
    _merge_db_values(
        catalog,
        "scheme_codes",
        "scheme_codes",
        [{"value": "EQ"}, {"value": "DEBT"}],
    )
    assert catalog["filters"]["scheme_codes"]["values"] == ["ALL", "DEBT", "EQ"]
    assert catalog["filters"]["scheme_codes"]["source"] == "db"


def test_filter_catalog_allows_and_prompt_summary():
    catalog = FilterCatalog(_contract_catalog())
    assert catalog.allows("eligibility", "YES")
    assert not catalog.allows("eligibility", "MAYBE")
    summary = catalog.prompt_summary()
    assert "eligibility" in summary
    assert "Catalog filter keys" in summary


def test_load_default_catalog_file(tmp_path: Path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_contract_catalog()), encoding="utf-8")
    loaded = load_catalog_from_file(path)
    assert loaded.get_values("investor_type") == ["ALL", "ACTIVE", "DORMANT"]


def test_refresh_without_database_writes_contract_only(tmp_path: Path, monkeypatch):
    output = tmp_path / "filter_catalog.json"
    catalog = refresh_catalog_from_db(database_url=None, output_path=output)
    assert output.exists()
    assert catalog.source in {"db+contract", "contract"}
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert "filters" in saved
    assert "eligibility" in saved["filters"]
