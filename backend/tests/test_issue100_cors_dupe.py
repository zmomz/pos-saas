"""ISSUE-100 guard: the duplicate CORS helper is gone and CORS comes only from
``core/cors.py``.

``middlewares/production.py`` once carried its own ``get_cors_config`` with
``yourdomain.com`` placeholder origins. ``core/cors.py`` is the single source of
truth (wired in ``main.py``). These tests fail until the duplicate — and its
placeholder origins — are removed.
"""
from pathlib import Path

import middlewares.production as production_module


def test_production_module_has_no_cors_config_duplicate():
    # The duplicate helper must not be importable from the middleware module.
    assert not hasattr(production_module, "get_cors_config")


def test_no_placeholder_origins_remain_in_production_source():
    src = Path(production_module.__file__).read_text(encoding="utf-8")
    assert "yourdomain.com" not in src


def test_cors_comes_only_from_core_cors():
    # The single source of truth still exposes the helper.
    import core.cors as cors_module

    assert callable(cors_module.get_cors_config)
