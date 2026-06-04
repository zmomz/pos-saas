"""F-025 / AG-05 + AG-06: deep white-label — custom domain + branded email.

AG-05: an agent claims a custom domain and a request arriving on that host (even
``https://WWW.host:443/path``) resolves the agent's branding *without auth* so the
merchant login/funnel is served under the agent's brand. Domains are unique across
agents. AG-06: the provisioning email is rendered through the agent's brand/template
(``render_provisioning_email`` is pure and unit-tested as the catch-forever anchor).
"""
import uuid

import pytest

from conftest import auth_headers, make_agent_account
from core.email import render_provisioning_email


def _unique_domain() -> str:
    return f"shop-{uuid.uuid4().hex[:10]}.example.com"


async def _set_domain(client, token, domain, **extra):
    return await client.put(
        "/api/v1/branding/update",
        json={"custom_domain": domain, **extra},
        headers=auth_headers(token),
    )


@pytest.mark.asyncio
async def test_branding_by_domain_resolves_agent_branding(client):
    _agent_user, agent_token, _agent_id = await make_agent_account(client)
    domain = _unique_domain()

    # The agent sets its domain (mixed-case + scheme) — it is stored normalized.
    resp = await _set_domain(client, agent_token, f"HTTPS://{domain.upper()}", primary_color="#ff0000")
    assert resp.status_code == 200, resp.text
    assert resp.json()["custom_domain"] == domain

    # A public (unauthenticated) request on that host resolves the agent's brand.
    r = await client.get("/api/v1/tenant/branding/by-domain", params={"domain": domain})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["company_name"] == "Agent Co"
    assert body["primary_color"] == "#ff0000"
    assert body["custom_domain"] == domain
    # The agent's email template is NOT exposed on the public path.
    assert body.get("email_template_subject") is None
    assert body.get("email_template_body") is None


@pytest.mark.asyncio
async def test_branding_by_domain_normalizes_www_port_and_scheme(client):
    _agent_user, agent_token, _agent_id = await make_agent_account(client)
    domain = _unique_domain()
    assert (await _set_domain(client, agent_token, domain)).status_code == 200

    # A Host header carrying scheme + www + port + path resolves the same agent.
    r = await client.get(
        "/api/v1/tenant/branding/by-domain",
        params={"domain": f"https://www.{domain}:443/login"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["company_name"] == "Agent Co"


@pytest.mark.asyncio
async def test_branding_by_domain_unknown_returns_404(client):
    # An unclaimed domain returns 404 (caller falls back to the platform theme).
    r = await client.get(
        "/api/v1/tenant/branding/by-domain",
        params={"domain": f"unclaimed-{uuid.uuid4().hex[:8]}.example.org"},
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_custom_domain_must_be_unique(client):
    _a1_user, a1_token, _a1_id = await make_agent_account(client)
    _a2_user, a2_token, _a2_id = await make_agent_account(client)
    domain = _unique_domain()

    assert (await _set_domain(client, a1_token, domain)).status_code == 200
    # A second agent cannot claim the same host (case-insensitively).
    clash = await _set_domain(client, a2_token, domain.upper())
    assert clash.status_code == 409, clash.text


@pytest.mark.asyncio
async def test_provisioning_email_uses_agent_template(client):
    # AG-06: when the agent supplies a template, it is rendered with placeholders.
    subject, body = render_provisioning_email(
        to_email="merchant@example.com",
        business_name="Falafel House",
        temp_password="t0p-secret",
        brand_name="Acme POS",
        login_url="https://pos.acme.sa/login",
        subject_template="مرحبا {business_name} — {brand}",
        body_template="Sign in at {login_url} with {email} / {password}",
    )
    assert subject == "مرحبا Falafel House — Acme POS"
    assert "https://pos.acme.sa/login" in body
    assert "merchant@example.com" in body
    assert "t0p-secret" in body


@pytest.mark.asyncio
async def test_provisioning_email_default_is_branded_not_platform(client):
    # AG-06: with no template the default still carries the agent's brand + login URL,
    # never a bare "POS"/platform identity.
    subject, body = render_provisioning_email(
        to_email="merchant@example.com",
        business_name="Falafel House",
        temp_password="t0p-secret",
        brand_name="Acme POS",
        login_url="https://pos.acme.sa/login",
    )
    assert "Acme POS" in subject
    assert "Acme POS" in body
    assert "https://pos.acme.sa/login" in body
