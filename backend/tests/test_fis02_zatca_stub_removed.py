"""FIS-02 — remove the stub ZATCA-XML endpoint and the orphan ZATCAService stamp.

``POST /api/v1/production/invoice/zatca-xml`` generated an unsigned, unpersisted
UBL document yet returned ``{"zatca_phase": 2}`` — presenting a dev/demo artifact
as if it were a compliant Phase-2 fiscal record. The real signing path lives in
``services/zatca_sale.py`` (driven from the sale itself) and ``routers/zatca.py``;
the stub had no legitimate caller. Its ``ZATCAService.generate_cryptographic_stamp``
(and the ``generate_invoice_hash`` / hash-normalisation helpers it relied on) were
orphaned alongside it.

These tests pin: the stub route is gone (404), the orphan stamp methods are
deleted, and the genuinely-live ``generate_xml_invoice`` (used by the real sale
path) is untouched.
"""
import main
from services.production import zatca_service

_STUB_PATH = "/api/v1/production/invoice/zatca-xml"


async def test_zatca_xml_stub_route_is_removed(client):
    """The stub endpoint no longer reaches a handler.

    With the POST route deleted the request is no longer served: it resolves to
    404, or 405 when a same-path GET catch-all (the SPA fallback) is mounted and
    rejects the POST method. Either way the stub's old ``zatca_phase: 2`` body is
    gone — the request never reaches a handler.
    """
    resp = await client.post(_STUB_PATH, json={"transaction_id": 1})
    assert resp.status_code in (404, 405), resp.text


def test_no_post_handler_registered_for_stub_path():
    """No registered route serves POST at the stub path (SPA-independent check)."""
    for route in main.app.routes:
        if getattr(route, "path", None) == _STUB_PATH:
            assert "POST" not in (route.methods or set())


def test_orphan_stamp_and_hash_methods_are_deleted():
    """The stub's orphan helpers are gone; only the live XML builder remains."""
    for dead in (
        "generate_cryptographic_stamp",
        "generate_invoice_hash",
        "_normalise_hash_to_b64_digest",
        "_next_sequential_number",
    ):
        assert not hasattr(zatca_service, dead), f"{dead} should be deleted"


def test_real_xml_invoice_builder_is_preserved():
    """``generate_xml_invoice`` (used by the real sale-signing path) is intact."""
    assert callable(getattr(zatca_service, "generate_xml_invoice", None))
