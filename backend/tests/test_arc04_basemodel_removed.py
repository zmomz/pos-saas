"""ARC-04 — the dead SQLAlchemy BaseModel class must stay removed.

models/base.py once declared an ``__abstract__`` ``BaseModel(Base)`` with id /
created_at / updated_at columns, but no model ever inherited it (every model
subclasses ``Base`` directly). It was dead surface. These guards keep it from
creeping back while protecting the one thing models/base.py legitimately does:
re-export ``Base``.
"""
import importlib


def test_basemodel_class_is_gone():
    # The orphan abstract base must not exist on the module any more.
    base_module = importlib.import_module("models.base")
    assert not hasattr(base_module, "BaseModel")


def test_base_reexport_is_preserved():
    # Models do `from models.base import Base`; that re-export must survive and
    # be the canonical declarative Base from core.database.
    from core.database import Base as CoreBase
    from models.base import Base as ModelsBase

    assert ModelsBase is CoreBase


def test_models_and_app_still_import():
    # The model packages that import from models.base, and the app, load cleanly.
    for name in (
        "models.auth",
        "models.mfa",
        "models.password_reset",
        "models.user_sessions",
        "models.user_profile",
        "main",
    ):
        assert importlib.import_module(name) is not None
