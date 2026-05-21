import json

from app.services import filter_catalog as filter_catalog_module
from app.services.filter_catalog import _contract_catalog, reload_filter_catalog
from app.services.filter_prompts import (
    SOURCE_OF_TRUTH_NOTICE,
    build_detect_intent_system_prompt,
    build_root_agent_instruction,
    build_search_plan_system_prompt,
)


def _use_catalog_file(monkeypatch, path):
    monkeypatch.setattr(filter_catalog_module, "_resolve_catalog_path", lambda: path)
    reload_filter_catalog()


def test_search_plan_prompt_includes_catalog_values(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    data = _contract_catalog()
    data["filters"]["systematic_plans"]["values"] = ["SIP", "NEWPLAN"]
    catalog_path.write_text(json.dumps(data), encoding="utf-8")

    _use_catalog_file(monkeypatch, catalog_path)

    prompt = build_search_plan_system_prompt()
    assert SOURCE_OF_TRUTH_NOTICE in prompt
    assert "NEWPLAN" in prompt
    assert '"eligibility": "ALL" | "YES" | "NO"' in prompt or '"YES"' in prompt
    assert "systematic_plans" in prompt


def test_detect_intent_prompt_includes_catalog_dimensions(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_contract_catalog()), encoding="utf-8")
    _use_catalog_file(monkeypatch, catalog_path)

    prompt = build_detect_intent_system_prompt()
    assert "activity_duration" in prompt
    assert "Recognized search filter dimensions" in prompt


def test_root_agent_prompt_includes_catalog_durations(monkeypatch, tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(_contract_catalog()), encoding="utf-8")
    _use_catalog_file(monkeypatch, catalog_path)

    prompt = build_root_agent_instruction()
    assert "1 month" in prompt
    assert "filter catalog" in prompt.lower()
