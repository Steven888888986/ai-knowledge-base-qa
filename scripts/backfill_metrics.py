"""Fill missing automatic estimates in saved QA history without adding questions."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import metrics


if __name__ == "__main__":
    result = metrics.backfill_missing()
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(1 if result["failed"] else 0)
