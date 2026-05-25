#!/usr/bin/env bash
# Point backend/.env DEV_DATABASE_URL at local Docker Postgres (after a successful clone).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
LOCAL_URL="${LOCAL_DATABASE_URL:-postgresql://localdev:localdev@localhost:5433/investor_db_local}"

python3 - "${ENV_FILE}" "${LOCAL_URL}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
local = sys.argv[2]
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()
out: list[str] = []
replaced = False
for line in lines:
    if line.strip().startswith("DEV_DATABASE_URL=") and not line.strip().startswith("#"):
        if not replaced:
            out.append(f"# Remote (previous): {line}")
            out.append(f"DEV_DATABASE_URL={local}")
            replaced = True
        continue
    out.append(line)
if not replaced:
    out.append(f"DEV_DATABASE_URL={local}")
local = sys.argv[2]
extra = [
    "USE_LOCAL_DOCKER_POSTGRES=true",
    f"LOCAL_DATABASE_URL={local}",
]
for line in extra:
    key = line.split("=", 1)[0]
    if not any(p.strip().startswith(f"{key}=") for p in out if not p.strip().startswith("#")):
        out.append(line)
path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
print(f"Updated {path} → USE_LOCAL_DOCKER_POSTGRES=true, LOCAL_DATABASE_URL")
PY
