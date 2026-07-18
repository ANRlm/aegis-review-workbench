#!/usr/bin/env python
"""Validate the five-class YOLO dataset used by Aegis Review."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aegis_review.cv.dataset import main

if __name__ == "__main__":
    raise SystemExit(main())
