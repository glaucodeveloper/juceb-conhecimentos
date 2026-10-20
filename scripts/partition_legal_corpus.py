#!/usr/bin/env python3
"""Generate one traceable OKF per extracted legal article candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from legal_corpus import build_legal_corpus  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="raiz da speciality com source-okfs/compiled/ (padrão: pasta do repositório)",
    )
    args = parser.parse_args()
    result = build_legal_corpus(args.root.expanduser().resolve())
    if result is None:
        raise SystemExit("Nenhum OKF compilado encontrado em source-okfs/compiled/")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
