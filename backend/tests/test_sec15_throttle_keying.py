"""SEC-15 — strengthen login-throttle keying.

The original ISSUE-043 guard locked only on a per-(identifier, IP) counter, so a
distributed credential-stuffing run that spreads its guesses across many source
IPs never tripped the lock for the targeted account — every individual pair
stayed below the threshold. SEC-15 adds two cross-cutting counters:

* a per-account counter that locks an identifier once enough failures accumulate
  *regardless of source IP* (defeats distributed spray against one account), and
* a per-IP counter that locks a source IP once enough failures accumulate
  *across all accounts* (defeats one host spraying many accounts). Its threshold
  is deliberately higher than the per-account one to limit NAT false positives.

These behaviors are exercised through the ``services.login_throttle`` API
directly because the HTTP login route fixes the client IP per request, and the
whole point here is varying the IP.
"""
from core.config import settings
from core.database import db_manager
from services.login_throttle import (
    LoginLockedOut,
    assert_login_allowed,
    clear_login_attempts,
    register_failed_login,
)


async def _is_locked(db, identifier: str, ip: str) -> bool:
    try:
        await assert_login_allowed(db, identifier, ip)
        return False
    except LoginLockedOut:
        return True


async def test_distributed_spray_against_one_account_locks_the_account(monkeypatch):
    # Per-pair threshold stays at the default 5; the account threshold is lowered
    # so the test is fast. Each source IP contributes only ONE failure — far
    # below the per-pair threshold — yet the account-wide counter must trip.
    monkeypatch.setattr(settings, "login_account_max_attempts", 4, raising=False)

    identifier = "victim@example.com"
    async with db_manager.async_session_maker() as db:
        # Three failures from three distinct IPs: under the account threshold.
        for i in range(3):
            await register_failed_login(db, identifier, f"10.0.0.{i}")
        assert not await _is_locked(db, identifier, "10.0.0.99")

        # The fourth distinct-IP failure crosses the per-account threshold, so a
        # subsequent attempt from a brand-new IP is now locked out.
        await register_failed_login(db, identifier, "10.0.0.4")
        assert await _is_locked(db, identifier, "10.0.0.99")


async def test_spray_from_one_ip_across_accounts_locks_the_ip(monkeypatch):
    # Keep the per-account threshold high so it can't be what trips — every
    # account sees only a single failure — and lower the per-IP threshold.
    monkeypatch.setattr(settings, "login_account_max_attempts", 100, raising=False)
    monkeypatch.setattr(settings, "login_ip_max_attempts", 4, raising=False)

    attacker_ip = "203.0.113.7"
    async with db_manager.async_session_maker() as db:
        # Three distinct accounts, one failure each from the attacker IP: under
        # the per-IP threshold, so a fresh account from that IP is still allowed.
        for i in range(3):
            await register_failed_login(db, f"user{i}@example.com", attacker_ip)
        assert not await _is_locked(db, "newcomer@example.com", attacker_ip)

        # The fourth distinct-account failure crosses the per-IP threshold: now
        # even a never-seen account from that IP is locked out...
        await register_failed_login(db, "user3@example.com", attacker_ip)
        assert await _is_locked(db, "newcomer@example.com", attacker_ip)

        # ...while the very same account from a *different* IP is unaffected —
        # the lock is keyed on the source IP, not the account.
        assert not await _is_locked(db, "newcomer@example.com", "198.51.100.2")


async def test_ip_spray_lock_survives_attacker_controlled_success(monkeypatch):
    # ISSUE-190: a host spraying many accounts must not be able to wipe its own
    # IP-wide lock by authenticating to a single account it controls.
    monkeypatch.setattr(settings, "login_account_max_attempts", 100, raising=False)
    monkeypatch.setattr(settings, "login_ip_max_attempts", 4, raising=False)

    attacker_ip = "203.0.113.42"
    async with db_manager.async_session_maker() as db:
        # Spray four distinct accounts from the attacker IP — trips the per-IP lock.
        for i in range(4):
            await register_failed_login(db, f"spray{i}@example.com", attacker_ip)
        assert await _is_locked(db, "victim@example.com", attacker_ip)

        # The attacker now signs in successfully to an account it owns from the
        # same IP. A genuine success clears that account's own counters, but it
        # must NOT reset the IP-wide spray lock.
        await clear_login_attempts(db, "attacker-owned@example.com", attacker_ip)
        assert await _is_locked(db, "victim@example.com", attacker_ip)


async def test_per_account_counter_still_clears_on_success(monkeypatch):
    # The legitimate account owner's success must still relieve that account's
    # own distributed-spray counter (the fix is scoped to the IP-wide row only).
    monkeypatch.setattr(settings, "login_account_max_attempts", 4, raising=False)
    monkeypatch.setattr(settings, "login_ip_max_attempts", 100, raising=False)

    identifier = "owner@example.com"
    async with db_manager.async_session_maker() as db:
        for i in range(4):
            await register_failed_login(db, identifier, f"10.1.0.{i}")
        assert await _is_locked(db, identifier, "10.1.0.99")

        await clear_login_attempts(db, identifier, "10.1.0.50")
        assert not await _is_locked(db, identifier, "10.1.0.99")


def test_per_ip_threshold_is_higher_than_per_account_by_default():
    # The IP counter aggregates across every account behind a (possibly NAT'd)
    # address, so its threshold must sit above the per-account one to avoid
    # locking out innocent co-tenants of a shared egress IP.
    assert settings.login_ip_max_attempts > settings.login_account_max_attempts
