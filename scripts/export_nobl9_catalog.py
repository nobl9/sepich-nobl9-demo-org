#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "catalog" / "org"
EXPORTS = (
    ("projects.yaml", ["sloctl", "get", "projects", "-o", "yaml"]),
    ("services.yaml", ["sloctl", "get", "services", "-A", "-o", "yaml"]),
    ("alertpolicies.yaml", ["sloctl", "get", "alertpolicies", "-A", "-o", "yaml"]),
    ("slos.yaml", ["sloctl", "get", "slos", "-A", "-o", "yaml"]),
)


def main() -> int:
    CATALOG_ROOT.mkdir(parents=True, exist_ok=True)

    for filename, command in EXPORTS:
        target = CATALOG_ROOT / filename
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            return result.returncode
        target.write_text(result.stdout, encoding="utf-8")
        print(f"Wrote {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
