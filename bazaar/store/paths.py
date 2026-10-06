"""Where local data lives, and the operator's Bazaar client."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def client():
    """The operator's team client. Needs `bazaar_sdk.py` from the official Bazaar kit at the repo root."""
    try:
        from bazaar_sdk import Bazaar
    except ImportError as exc:
        raise SystemExit("bazaar_sdk.py not found: copy it from the official Bazaar kit into the repo root.") from exc
    load_env()
    return Bazaar(os.environ.get("BAZAAR_URL", "https://bazaar.causaprima.ai"), os.environ["BAZAAR_KEY"])
