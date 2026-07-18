#!/usr/bin/env python
"""Validate the five-class YOLO dataset used by Aegis Review."""

from __future__ import annotations

import sys

from aegis_review.cv.dataset import main

if __name__ == "__main__":
    raise SystemExit(main())
