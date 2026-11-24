"""Run existing metrics E2E while preserving all historical auto-metrics files.

The called script uses an isolated temporary SQLite and headless Edge. Its human
review entries are deliberate test inputs, never factual production judgments.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
backups = {path: path.read_bytes() for path in EVIDENCE.glob("auto-metrics-*") if path.is_file()}
before = {path.name: hashlib.sha256(data).hexdigest() for path, data in backups.items()}
result = {}
try:
    run = subprocess.run([sys.executable, str(EVIDENCE / "live-metrics-ui.py")], cwd=ROOT,
                         env={**os.environ, "PYTHONUTF8": "1"}, capture_output=True, text=True,
                         encoding="utf-8", timeout=180,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if run.returncode:
        result = {"passed": False, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
    else:
        result = json.loads((EVIDENCE / "auto-metrics-ui.json").read_text(encoding="utf-8"))
finally:
    for path, data in backups.items():
        path.write_bytes(data)
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in backups}
    result["historical_evidence_restored"] = before == after
    result["historical_evidence_sha256"] = after
    result["runner"] = "existing docs/evidence/live-metrics-ui.py"
    (EVIDENCE / "numeric-lookup-metrics-regression.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result.get("passed"), "checks": len(result.get("checks", [])),
                      "historical_evidence_restored": result["historical_evidence_restored"]}))

if not result.get("passed"):
    raise SystemExit(1)
