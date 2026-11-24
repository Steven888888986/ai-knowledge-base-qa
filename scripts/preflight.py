"""Deterministic Stop-hook checks; any failed child process blocks completion."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(rb"(?i)\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".runtime", "models"}


def scan_files():
    for current, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = Path(current) / name
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".sqlite", ".sqlite3", ".db", ".pyc"}:
                continue
            yield path


def find_secrets(paths):
    findings = []
    for path in paths:
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def main():
    secrets = find_secrets(scan_files())
    if secrets:
        print("FAIL: probable API token found in " + ", ".join(secrets), file=sys.stderr)
        return 1
    for command in ([sys.executable, "-m", "compileall", "-q", "app.py", "server.py", "metrics.py", "mcp_server.py", "scripts", "tests"],
                    [sys.executable, "tests/test_app.py"]):
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            print(f"FAIL: {command} exited {result.returncode}", file=sys.stderr)
            return result.returncode
    print("PASS: compile, deterministic app/MCP tests, and secret scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
