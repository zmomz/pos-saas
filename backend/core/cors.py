"""CORS configuration helper.

Resolves the kwargs passed to FastAPI's ``CORSMiddleware`` from settings so the
origin policy is environment-aware instead of the previous blanket
``allow_origin_regex=r".*"`` (which allows every origin with credentials).

Policy:
- If ``ALLOWED_ORIGINS`` is set (comma-separated), those exact origins are used.
- Else, in ``ENVIRONMENT=dev`` we fall back to allowing any origin (developer
  convenience) — but WITHOUT credentials, since ``allow_credentials=True`` plus a
  wildcard origin is rejected by browsers anyway.
- Else (prod, no list configured) we lock down to common localhost dev origins so
  a misconfigured deployment fails closed rather than open.
"""
import os
from typing import Any, Dict, List

from core.config import settings

# Sensible localhost defaults for the Vite dev server / preview.
_LOCALHOST_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _parse_origins(raw: str) -> List[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_cors_config() -> Dict[str, Any]:
    """Build the keyword arguments for ``CORSMiddleware`` based on settings."""
    base: Dict[str, Any] = {
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        "expose_headers": ["*"],
    }

    configured = _parse_origins(getattr(settings, "allowed_origins", "") or "")
    if configured:
        return {
            **base,
            "allow_origins": configured,
            "allow_credentials": True,
        }

    is_dev = os.getenv("ENVIRONMENT", "prod").lower() == "dev"
    if is_dev:
        # Any origin, but credentials disabled (wildcard + credentials is invalid).
        return {
            **base,
            "allow_origin_regex": r".*",
            "allow_credentials": False,
        }

    # Prod with no explicit list: fail closed to localhost only.
    return {
        **base,
        "allow_origins": _LOCALHOST_ORIGINS,
        "allow_credentials": True,
    }
