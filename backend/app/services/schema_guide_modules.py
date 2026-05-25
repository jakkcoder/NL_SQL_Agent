"""Modular investor schema guide: select sections by question, assemble slim LLM payload."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MODULES_DIR = Path(__file__).resolve().parents[1] / "data" / "schema_guide_modules"
_MANIFEST_PATH = _MODULES_DIR / "manifest.json"

# Always sent (ARN anchor + investor list).
CORE_MODULE_ID = "core_arn_investor"

# Fallback when no keyword hits (generic list/filter).
_DEFAULT_MODULE_IDS = (CORE_MODULE_ID, "geography_city", "investor_filters")


def _normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    if not _MANIFEST_PATH.is_file():
        return {"version": 0, "modules": []}
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def load_module(module_id: str) -> dict[str, Any] | None:
    path = _MODULES_DIR / f"{module_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _slim_table(table: dict[str, Any], *, include_sample: bool = False) -> dict[str, Any]:
    cols = []
    for col in table.get("columns") or []:
        if not isinstance(col, dict):
            continue
        cols.append(
            {
                "name": col.get("name"),
                "type": col.get("type"),
                "description": col.get("description"),
            }
        )
    out: dict[str, Any] = {
        "fully_qualified": table.get("fully_qualified"),
        "purpose": table.get("purpose"),
        "columns": cols,
    }
    if include_sample and table.get("sample_row"):
        out["sample_row"] = table["sample_row"]
    return out


def _tables_from_module(mod: dict[str, Any]) -> list[dict[str, Any]]:
    return [_slim_table(t) for t in mod.get("tables") or [] if isinstance(t, dict)]


def select_module_ids_keyword(
    question: str,
    *,
    repair_context: dict[str, Any] | None = None,
    max_modules: int = 5,
) -> list[str]:
    """Keyword router: pick guide module ids (always includes core). Fallback when LLM router fails."""

    manifest = load_manifest()
    modules_meta = manifest.get("modules") or []
    if not modules_meta:
        return list(_DEFAULT_MODULE_IDS)

    q = _normalize_question(question)
    scored: list[tuple[int, str]] = []

    for entry in modules_meta:
        if not isinstance(entry, dict):
            continue
        mid = str(entry.get("id") or "")
        if not mid or mid == CORE_MODULE_ID:
            continue
        if entry.get("always_include"):
            scored.append((1000, mid))
            continue
        score = 0
        for kw in entry.get("keywords") or []:
            token = str(kw).strip().lower()
            if token and token in q:
                score += 10 if " " in token else 3
        for pattern in entry.get("phrase_patterns") or []:
            if pattern and re.search(pattern, q, re.IGNORECASE):
                score += 15
        if score > 0:
            scored.append((score, mid))

    if repair_context:
        failed_sql = str(repair_context.get("failed_sql") or "").lower()
        for entry in modules_meta:
            mid = str(entry.get("id") or "")
            for marker in entry.get("sql_table_markers") or []:
                if marker and str(marker).lower() in failed_sql:
                    scored.append((50, mid))

    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen: list[str] = [CORE_MODULE_ID]
    for _score, mid in scored:
        if mid not in chosen:
            chosen.append(mid)
        if len(chosen) >= max_modules:
            break

    if len(chosen) == 1:
        chosen.extend(m for m in _DEFAULT_MODULE_IDS if m not in chosen)
    return chosen[: max(1, max_modules)]


def assemble_guide_from_modules(module_ids: list[str]) -> dict[str, Any]:
    """Merge module JSON files into one guide object for the SQL generator."""

    manifest = load_manifest()
    tables_by_fq: dict[str, dict[str, Any]] = {}
    recipes_by_name: dict[str, dict[str, str]] = {}
    patterns: list[dict[str, Any]] = []
    vocab: dict[str, Any] = {}
    summaries: list[dict[str, str]] = []

    for mid in module_ids:
        mod = load_module(mid)
        if not mod:
            logger.warning("Schema guide module missing: %s", mid)
            continue
        summaries.append({"id": mid, "summary": str(mod.get("summary") or "")})
        for recipe in mod.get("join_recipes") or []:
            if isinstance(recipe, dict) and recipe.get("name"):
                recipes_by_name[str(recipe["name"])] = recipe
        for table in _tables_from_module(mod):
            fq = table.get("fully_qualified")
            if fq:
                tables_by_fq[str(fq)] = table
        for pattern in mod.get("question_patterns") or []:
            if isinstance(pattern, dict):
                patterns.append(pattern)
        mod_vocab = mod.get("filter_vocabulary")
        if isinstance(mod_vocab, dict):
            vocab.update(mod_vocab)

    global_rules = manifest.get("sql_rules") or {}
    return {
        "contract_kind": "investor_schema_guide",
        "payload_kind": "modular_sections",
        "module_ids": list(module_ids),
        "module_summaries": summaries,
        "purpose": (
            "Modular schema guide: only sections relevant to the user question. "
            "Use module_summaries + tables + join_recipes + question_patterns."
        ),
        "sql_rules": {
            **global_rules,
            "modular": "Do not reference tables absent from this payload; request is scoped to selected modules.",
        },
        "join_recipes": list(recipes_by_name.values()),
        "filter_vocabulary": vocab,
        "question_patterns": patterns,
        "tables": list(tables_by_fq.values()),
        "table_count": len(tables_by_fq),
    }


def build_guide_payload_for_question(
    question: str,
    *,
    repair_context: dict[str, Any] | None = None,
    max_chars: int = 48_000,
    max_modules: int = 5,
) -> tuple[str, list[str], dict[str, Any]]:
    """Return JSON string for ``investor_schema_guide_json``, module ids, and selection meta."""

    from app.services.schema_guide_module_router import select_module_ids_for_question

    module_ids, selection_meta = select_module_ids_for_question(
        question, repair_context=repair_context, max_modules=max_modules
    )
    guide = assemble_guide_from_modules(module_ids)
    selection_meta["module_ids"] = module_ids
    raw = json.dumps(guide, ensure_ascii=True, default=str)
    if len(raw) > max_chars:
        # Drop question pattern sql_skeleton bodies first
        for pat in guide.get("question_patterns") or []:
            if isinstance(pat, dict) and "sql_skeleton" in pat:
                pat.pop("sql_skeleton", None)
        raw = json.dumps(guide, ensure_ascii=True, default=str)
    if len(raw) > max_chars:
        raw = raw[: max_chars - 80] + "\n...(modular guide truncated)\n"
    return raw, module_ids, selection_meta


def modular_guide_available() -> bool:
    return _MANIFEST_PATH.is_file() and any(_MODULES_DIR.glob("*.json"))


def manifest_summaries_for_system_prompt() -> str:
    """Compact index of modules for the static system prompt."""

    manifest = load_manifest()
    lines = ["## Schema guide modules (router picks 1–5 per question)", ""]
    for entry in manifest.get("modules") or []:
        if not isinstance(entry, dict):
            continue
        mid = entry.get("id", "")
        summary = entry.get("summary", "")
        kws = entry.get("keywords") or []
        kw_preview = ", ".join(str(k) for k in kws[:8])
        if len(kws) > 8:
            kw_preview += ", …"
        lines.append(f"- **{mid}**: {summary} (keywords: {kw_preview or '—'})")
    return "\n".join(lines)
