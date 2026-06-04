"""AG-03 (F-026): an agent's per-client feature toggle actually gates server-side.

Before this finding, ``require_feature`` enforced only ``email_receipts`` /
``sms_receipts`` / ``loyalty``; the other agent-facing toggles
(``inventory`` / ``discounts`` / ``zatca`` / ``omnichannel``) were stored but
never checked — cosmetic switches. This pins the real behaviour:

  * a feature is enabled by default (no ``client_features`` row → allowed);
  * disabling ``inventory`` for a client 403s the inventory routes;
  * disabling ``discounts`` for a client 403s the discount-apply (validate) path;
  * the toggle endpoint rejects an unknown feature name (400) instead of silently
    storing a switch that gates nothing, and accepts every enumerated key.

Owner scoping for the toggle itself is covered by the existing tenant tests; here
we drive the toggle through the real agent endpoint so the enum + the gate are
exercised end-to-end.
"""
import pytest

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)
from dependencies.features import FEATURE_KEYS


async def _set_feature(client, agent_token, client_id, feature_name, is_enabled):
    return await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/features",
        json={"feature_name": feature_name, "is_enabled": is_enabled},
        headers=auth_headers(agent_token),
    )


@pytest.mark.asyncio
async def test_disabled_inventory_feature_blocks_inventory_route(client):
    """Default-enabled inventory works; disabling it 403s the inventory route."""
    _au, agent_token, agent_id = await make_agent_account(client)
    _cu, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Enabled by default: no client_features row → the route is reachable.
    ok = await client.get(
        "/api/v1/inventory/alerts", headers=auth_headers(client_token)
    )
    assert ok.status_code == 200, ok.text

    # Agent disables the inventory feature for this client.
    toggle = await _set_feature(client, agent_token, client_id, "inventory", False)
    assert toggle.status_code == 200, toggle.text

    # Now the governed route is gated server-side.
    blocked = await client.get(
        "/api/v1/inventory/alerts", headers=auth_headers(client_token)
    )
    assert blocked.status_code == 403, blocked.text


@pytest.mark.asyncio
async def test_disabled_discounts_feature_blocks_discount_validate(client):
    """Disabling ``discounts`` 403s the discount-apply path before the handler runs."""
    _au, agent_token, agent_id = await make_agent_account(client)
    _cu, client_token, client_id = await make_client_under_agent(client, agent_id)

    body = {"code": "SAVE10", "subtotal": 100.0}

    # Enabled by default: the gate passes, so the handler runs and rejects the
    # unknown code with 400 (NOT 403) — proving 403 below is the feature gate.
    enabled = await client.post(
        "/api/v1/entities/discounts/validate",
        json=body,
        headers=auth_headers(client_token),
    )
    assert enabled.status_code != 403, enabled.text

    # Agent disables the discounts feature for this client.
    toggle = await _set_feature(client, agent_token, client_id, "discounts", False)
    assert toggle.status_code == 200, toggle.text

    blocked = await client.post(
        "/api/v1/entities/discounts/validate",
        json=body,
        headers=auth_headers(client_token),
    )
    assert blocked.status_code == 403, blocked.text


@pytest.mark.asyncio
async def test_unknown_feature_name_rejected(client):
    """A feature name outside the enumerated set is rejected (400), not stored."""
    _au, agent_token, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)

    resp = await _set_feature(client, agent_token, client_id, "teleport", False)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_known_feature_names_accepted(client):
    """Every enumerated feature key is accepted by the toggle endpoint."""
    _au, agent_token, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)

    for feature_name in sorted(FEATURE_KEYS):
        resp = await _set_feature(client, agent_token, client_id, feature_name, True)
        assert resp.status_code == 200, f"{feature_name}: {resp.text}"
        assert resp.json()["feature_name"] == feature_name
