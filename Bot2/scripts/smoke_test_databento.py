#!/usr/bin/env python3
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_bots.smoke import run_databento_smoke_test


if __name__ == "__main__":
    result = run_databento_smoke_test()
    print(json.dumps(result, indent=2, ensure_ascii=False))
