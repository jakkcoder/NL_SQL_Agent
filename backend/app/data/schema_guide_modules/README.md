# Modular schema guide (LLM context)

The monolithic `investor_db_schema_guide.json` is too large for Bedrock context. SQL generation uses **selected modules** from this folder.

## Layout

| File | Role |
|------|------|
| `manifest.json` | Module index: `summary`, `keywords`, routing metadata |
| `{module_id}.json` | Tables, join recipes, question patterns, filter vocabulary slice |

## Rebuild after guide changes

```bash
cd backend && export PYTHONPATH=.
python scripts/build_schema_guide_modules.py
```

Run after updating `investor_db_schema_guide.json` or `investor_schema_question_patterns.py`.

## Runtime

1. **Module router LLM** (`app/services/schema_guide_module_router.py`) — small/fast model reads `question` + module summaries from `manifest.json`, returns JSON: `{"thought":"…","selected_module_ids":[…]}`.
2. **Assembler** merges those module JSON files into `investor_schema_guide_json` for the SQL generator.

Prompt: `SCHEMA_GUIDE_MODULE_ROUTER_SYSTEM_PROMPT` in `app/agents/system_prompts.py`.

On router failure, keyword fallback runs if `QUERY_GENERATOR_MODULE_ROUTER_KEYWORD_FALLBACK=true`.

Config:

- `QUERY_GENERATOR_MODULAR_GUIDE=true`
- `QUERY_GENERATOR_MODULE_ROUTER_LLM=true`
- `QUERY_GENERATOR_GUIDE_MAX_MODULES=5`
- `BEDROCK_MODULE_ROUTER_MODEL_ID` (optional; defaults to root/Haiku via `ROUTER_LLM_MODEL` / `BEDROCK_MODEL_ID`)
