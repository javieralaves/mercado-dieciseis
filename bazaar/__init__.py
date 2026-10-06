"""Mercado Dieciséis: private multi-team trade coordination for The Bazaar.

Domain code lives in the subpackages. The scripts at the repo root call into them.
"""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
