"""Issue #216 — staff lifecycle: suspend/terminate, attendance, shifts, PIN login.

Exercises the workforce-management surface end to end through the API:

* suspend / terminate revoke the staff member's *own* login immediately and a
  reactivate restores it;
* attendance clock-in / clock-out produce records with derived hours and export
  as CSV;
* shift assignment rosters a planned window;
* PIN login mints tokens for an active staff member and is refused once they are
  suspended.
"""
from conftest import auth_headers, make_client_account


async def _create_staff(client, owner_token, *, email, role="cashier"):
    """Create a staff member via the API (provisions a bound login)."""
    resp = await client.post(
        "/api/v1/entities/staff_members",
        headers=auth_headers(owner_token),
        json={"name": "Cashier", "email": email, "role": role, "is_active": True},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_suspend_revokes_staff_access(client):
    owner, owner_token, _ = await make_client_account(client)
    staff_email = "staff_suspend@example.com"
    created = await _create_staff(client, owner_token, email=staff_email)
    temp_password = created["temp_password"]
    assert temp_password, "a fresh staff login should return a one-time password"
    assert created["status"] == "active"

    # Staff can authenticate and reach their own state.
    login = await client.post(
        "/api/v1/auth/login", json={"email": staff_email, "password": temp_password}
    )
    assert login.status_code == 200, login.text
    staff_token = login.json()["token"]
    me = await client.get("/api/v1/auth/me", headers=auth_headers(staff_token))
    assert me.status_code == 200, me.text

    # Owner suspends the staff member.
    resp = await client.post(
        f"/api/v1/entities/staff_members/{created['id']}/suspend",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "suspended"
    assert resp.json()["is_active"] is False

    # The previously-issued token is dead (security stamp bumped) ...
    me_after = await client.get("/api/v1/auth/me", headers=auth_headers(staff_token))
    assert me_after.status_code == 401, me_after.text

    # ... and even a fresh login is blocked at the auth layer.
    relogin = await client.post(
        "/api/v1/auth/login", json={"email": staff_email, "password": temp_password}
    )
    assert relogin.status_code == 200, relogin.text
    me_relogin = await client.get(
        "/api/v1/auth/me", headers=auth_headers(relogin.json()["token"])
    )
    assert me_relogin.status_code == 403, me_relogin.text
    assert "revoked" in me_relogin.json()["detail"].lower()


async def test_reactivate_restores_access(client):
    owner, owner_token, _ = await make_client_account(client)
    staff_email = "staff_reactivate@example.com"
    created = await _create_staff(client, owner_token, email=staff_email)

    await client.post(
        f"/api/v1/entities/staff_members/{created['id']}/suspend",
        headers=auth_headers(owner_token),
    )
    resp = await client.post(
        f"/api/v1/entities/staff_members/{created['id']}/reactivate",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": staff_email, "password": created["temp_password"]},
    )
    me = await client.get(
        "/api/v1/auth/me", headers=auth_headers(login.json()["token"])
    )
    assert me.status_code == 200, me.text


async def test_terminate_revokes_access(client):
    owner, owner_token, _ = await make_client_account(client)
    staff_email = "staff_terminate@example.com"
    created = await _create_staff(client, owner_token, email=staff_email)

    resp = await client.post(
        f"/api/v1/entities/staff_members/{created['id']}/terminate",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "terminated"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": staff_email, "password": created["temp_password"]},
    )
    me = await client.get(
        "/api/v1/auth/me", headers=auth_headers(login.json()["token"])
    )
    assert me.status_code == 403, me.text


async def test_attendance_clock_in_out_and_export(client):
    owner, owner_token, _ = await make_client_account(client)
    created = await _create_staff(client, owner_token, email="staff_attend@example.com")
    sid = created["id"]

    ci = await client.post(
        f"/api/v1/entities/staff_members/{sid}/attendance/clock-in",
        headers=auth_headers(owner_token),
        json={"notes": "morning"},
    )
    assert ci.status_code == 201, ci.text
    assert ci.json()["clock_out"] is None

    # A second clock-in while still open is rejected.
    dup = await client.post(
        f"/api/v1/entities/staff_members/{sid}/attendance/clock-in",
        headers=auth_headers(owner_token),
        json={},
    )
    assert dup.status_code == 400, dup.text

    co = await client.post(
        f"/api/v1/entities/staff_members/{sid}/attendance/clock-out",
        headers=auth_headers(owner_token),
    )
    assert co.status_code == 200, co.text
    assert co.json()["clock_out"] is not None
    assert co.json()["hours"] is not None and co.json()["hours"] >= 0

    listing = await client.get(
        f"/api/v1/entities/staff_members/{sid}/attendance",
        headers=auth_headers(owner_token),
    )
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1

    export = await client.get(
        "/api/v1/entities/staff_members/attendance/export",
        headers=auth_headers(owner_token),
    )
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("text/csv")
    body = export.text
    assert "staff_id,staff_name" in body
    assert str(sid) in body


async def test_clock_out_without_clock_in_rejected(client):
    owner, owner_token, _ = await make_client_account(client)
    created = await _create_staff(client, owner_token, email="staff_noclock@example.com")
    resp = await client.post(
        f"/api/v1/entities/staff_members/{created['id']}/attendance/clock-out",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 400, resp.text


async def test_shift_assignment_lifecycle(client):
    owner, owner_token, _ = await make_client_account(client)
    created = await _create_staff(client, owner_token, email="staff_shift@example.com")
    sid = created["id"]

    assign = await client.post(
        f"/api/v1/entities/staff_members/{sid}/shifts",
        headers=auth_headers(owner_token),
        json={
            "starts_at": "2026-07-01T09:00:00+00:00",
            "ends_at": "2026-07-01T17:00:00+00:00",
            "role": "cashier",
        },
    )
    assert assign.status_code == 201, assign.text
    shift_id = assign.json()["id"]
    assert assign.json()["status"] == "scheduled"

    # End before start is rejected.
    bad = await client.post(
        f"/api/v1/entities/staff_members/{sid}/shifts",
        headers=auth_headers(owner_token),
        json={
            "starts_at": "2026-07-01T17:00:00+00:00",
            "ends_at": "2026-07-01T09:00:00+00:00",
        },
    )
    assert bad.status_code == 400, bad.text

    listing = await client.get(
        f"/api/v1/entities/staff_members/{sid}/shifts",
        headers=auth_headers(owner_token),
    )
    assert listing.status_code == 200 and len(listing.json()) == 1

    cancel = await client.delete(
        f"/api/v1/entities/staff_members/shifts/{shift_id}",
        headers=auth_headers(owner_token),
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"


async def test_pin_login(client):
    owner, owner_token, _ = await make_client_account(client)
    created = await _create_staff(client, owner_token, email="staff_pin@example.com")
    sid = created["id"]

    # Set a PIN.
    setpin = await client.put(
        f"/api/v1/entities/staff_members/{sid}/pin",
        headers=auth_headers(owner_token),
        json={"pin": "4821"},
    )
    assert setpin.status_code == 200, setpin.text

    # PIN login scoped to the merchant succeeds and yields a usable token.
    login = await client.post(
        "/api/v1/auth/login/pin",
        json={"merchant_email": owner["email"], "pin": "4821"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert me.status_code == 200, me.text

    # Wrong PIN is refused.
    bad = await client.post(
        "/api/v1/auth/login/pin",
        json={"merchant_email": owner["email"], "pin": "0000"},
    )
    assert bad.status_code == 401, bad.text


async def test_pin_login_blocked_after_suspend(client):
    owner, owner_token, _ = await make_client_account(client)
    created = await _create_staff(client, owner_token, email="staff_pin2@example.com")
    sid = created["id"]
    await client.put(
        f"/api/v1/entities/staff_members/{sid}/pin",
        headers=auth_headers(owner_token),
        json={"pin": "135790"},
    )
    await client.post(
        f"/api/v1/entities/staff_members/{sid}/suspend",
        headers=auth_headers(owner_token),
    )
    login = await client.post(
        "/api/v1/auth/login/pin",
        json={"merchant_email": owner["email"], "pin": "135790"},
    )
    assert login.status_code == 401, login.text


async def test_invalid_pin_rejected_on_set(client):
    owner, owner_token, _ = await make_client_account(client)
    created = await _create_staff(client, owner_token, email="staff_pin3@example.com")
    resp = await client.put(
        f"/api/v1/entities/staff_members/{created['id']}/pin",
        headers=auth_headers(owner_token),
        json={"pin": "12"},
    )
    assert resp.status_code == 400, resp.text


async def test_lifecycle_cross_tenant_isolation(client):
    owner_a, token_a, _ = await make_client_account(client)
    owner_b, token_b, _ = await make_client_account(client)
    created = await _create_staff(client, token_a, email="staff_iso@example.com")

    # Owner B cannot suspend owner A's staff.
    resp = await client.post(
        f"/api/v1/entities/staff_members/{created['id']}/suspend",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text
