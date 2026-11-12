"""Resolve the JAMSTEC project root for production and isolated checks."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
ROOT_ENV = "JAMSTEC_MULTIBEAM_ROOT"
PROJECT_ROOT = Path(os.environ.get(ROOT_ENV, PACKAGE_ROOT)).resolve()
