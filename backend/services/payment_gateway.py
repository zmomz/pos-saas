"""Pluggable Saudi payment gateway abstraction (PAY-01..06, F-001/F-002).

Turns a "card"/"Mada" tender from a label into a **real captured approval**. A
card-like tender is pushed to a gateway which either approves (returning the
acquirer network + approval/auth code + RRN + a refund-to-origin reference) or
declines — and a decline rolls the whole sale back (PAY-05).

Two concrete gateways live behind one interface so the rest of the app never
knows which provider ran:

* :class:`SandboxGateway` — deterministic, dependency-free. Approves by default
  and declines on an explicit ``simulate="decline"`` hint (used by tests and by
  un-onboarded installs so the POS still demonstrably captures/declines without
  real credentials — the OPS-08 graceful-degradation path).
* :class:`MoyasarGateway` — the first real Saudi adapter (Mada / Apple Pay / STC
  Pay / cards). It is selected automatically once ``MOYASAR_API_KEY`` is set; a
  card-like charge needs a gateway ``token`` produced by Moyasar's client-side
  tokenization (no PAN ever reaches us — PAY-09). Without a key/token it raises
  :class:`GatewayNotConfigured` and the resolver falls back to the sandbox.

Provider split (per INTENDED_BEHAVIOR.md §4.6): Moyasar first for online/Mada;
Tap/HyperPay/PayTabs slot in behind this same interface later, and in-store
SoftPOS terminal capture (Geidea, PAY-05/HW-03) is a separate adapter/finding.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tender taxonomy (PAY-01..04)
# ---------------------------------------------------------------------------
# Every tender type the POS understands. The Saudi-real set (mada/applepay/
# stcpay/tabby/tamara) is first-class; cash/transfer/loyalty settle internally.
SUPPORTED_TENDER_TYPES: tuple[str, ...] = (
    "cash",
    "card",
    "mada",
    "applepay",
    "stcpay",
    "tabby",
    "tamara",
    "transfer",
    "loyalty",
)

# Tenders that must capture a real gateway approval before the sale can complete.
# cash is physical, transfer is settled out-of-band, loyalty is an internal
# ledger move — none of those route to a gateway.
CARD_LIKE_TENDERS: frozenset[str] = frozenset(
    {"card", "mada", "applepay", "stcpay", "tabby", "tamara"}
)

# Map a tender type to the acquirer network label the sandbox reports.
_SANDBOX_NETWORK = {
    "card": "VISA",
    "mada": "MADA",
    "applepay": "APPLEPAY",
    "stcpay": "STCPAY",
    "tabby": "TABBY",
    "tamara": "TAMARA",
}


def normalize_tender_type(method: Optional[str]) -> str:
    """Map a (possibly legacy) method label onto a canonical tender type."""
    m = (method or "cash").strip().lower()
    aliases = {
        "bank_transfer": "transfer",
        "apple_pay": "applepay",
        "stc_pay": "stcpay",
        "stcpay": "stcpay",
        "credit": "card",
        "debit": "card",
    }
    m = aliases.get(m, m)
    return m if m in SUPPORTED_TENDER_TYPES else "card"


def requires_capture(tender_type: str) -> bool:
    """True when this tender must obtain a real gateway approval."""
    return normalize_tender_type(tender_type) in CARD_LIKE_TENDERS


# ---------------------------------------------------------------------------
# Result + error types
# ---------------------------------------------------------------------------
@dataclass
class GatewayResult:
    """Outcome of a gateway charge/refund. Carries only PCI-safe fields."""

    approved: bool
    gateway: str
    network: Optional[str] = None
    approval_code: Optional[str] = None
    rrn: Optional[str] = None
    gateway_ref: Optional[str] = None
    last4: Optional[str] = None
    token: Optional[str] = None
    decline_reason: Optional[str] = None


class PaymentDeclined(Exception):
    """Raised when a gateway declines a charge (the sale must roll back)."""

    def __init__(self, reason: str, gateway: str = "unknown"):
        super().__init__(reason)
        self.reason = reason
        self.gateway = gateway


class GatewayNotConfigured(Exception):
    """Raised when a real gateway is selected but lacks credentials/inputs."""


# ---------------------------------------------------------------------------
# Gateway interface
# ---------------------------------------------------------------------------
class PaymentGateway:
    """Abstract Saudi payment gateway. Concrete adapters implement charge/refund."""

    name: str = "abstract"

    async def charge(
        self,
        amount: float,
        tender_type: str,
        *,
        currency: str = "SAR",
        token: Optional[str] = None,
        simulate: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> GatewayResult:  # pragma: no cover - abstract
        raise NotImplementedError

    async def refund(self, gateway_ref: str, amount: float) -> GatewayResult:  # pragma: no cover
        raise NotImplementedError


class SandboxGateway(PaymentGateway):
    """Deterministic, credential-free gateway for dev/CI/un-onboarded installs.

    Approves every card-like charge and synthesizes a PCI-safe approval, unless
    ``simulate="decline"`` is passed (so the decline-blocks-the-sale invariant is
    testable without a live acquirer). This is **not** a money movement — it is a
    clearly-sandboxed stand-in until a real gateway is configured (OPS-08).
    """

    name = "sandbox"

    async def charge(
        self,
        amount: float,
        tender_type: str,
        *,
        currency: str = "SAR",
        token: Optional[str] = None,
        simulate: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> GatewayResult:
        tender_type = normalize_tender_type(tender_type)
        if (simulate or "").strip().lower() == "decline":
            return GatewayResult(
                approved=False,
                gateway=self.name,
                decline_reason="sandbox_forced_decline",
            )
        ref = uuid.uuid4().hex
        return GatewayResult(
            approved=True,
            gateway=self.name,
            network=_SANDBOX_NETWORK.get(tender_type, "VISA"),
            approval_code=ref[:6].upper(),
            rrn=ref[6:18],
            gateway_ref=f"sbx_{ref}",
            last4=(token or ref)[-4:],
            token=token or f"tok_sbx_{ref[:16]}",
        )

    async def refund(self, gateway_ref: str, amount: float) -> GatewayResult:
        ref = uuid.uuid4().hex
        return GatewayResult(
            approved=True,
            gateway=self.name,
            gateway_ref=f"rfnd_{ref}",
            approval_code=ref[:6].upper(),
        )


class MoyasarGateway(PaymentGateway):
    """Real Moyasar adapter (online Mada / Apple Pay / STC Pay / cards).

    Requires ``MOYASAR_API_KEY`` (the secret key) and, for a card-like charge, a
    ``token`` from Moyasar's client-side tokenization — the PAN is entered in
    Moyasar's iframe and never reaches us (PAY-09). Amounts are charged in the
    smallest currency unit (halalas for SAR).

    NOTE: this adapter is implemented but **inactive until a live key is set**.
    Wiring real credentials is an operator step (see the hand-off note).
    """

    name = "moyasar"
    _BASE_URL = "https://api.moyasar.com/v1"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def charge(
        self,
        amount: float,
        tender_type: str,
        *,
        currency: str = "SAR",
        token: Optional[str] = None,
        simulate: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> GatewayResult:
        if not token:
            # A card-like Moyasar charge needs a client-side source token.
            raise GatewayNotConfigured(
                "Moyasar charge requires a client-side payment token (no PAN on the server)"
            )
        import httpx  # local import keeps module import cheap

        amount_minor = int(round(amount * 100))
        payload = {
            "amount": amount_minor,
            "currency": currency,
            "source": {"type": "token", "token": token},
            "description": (metadata or {}).get("description", "POS sale"),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{self._BASE_URL}/payments",
                    json=payload,
                    auth=(self._api_key, ""),
                )
        except httpx.HTTPError as exc:  # network-level failure
            raise PaymentDeclined(f"moyasar network error: {exc}", gateway=self.name)

        if resp.status_code >= 500:
            raise PaymentDeclined(f"moyasar server error {resp.status_code}", gateway=self.name)
        body = resp.json() if resp.content else {}
        status = (body.get("status") or "").lower()
        source = body.get("source") or {}
        if status in ("paid", "authorized", "captured"):
            return GatewayResult(
                approved=True,
                gateway=self.name,
                network=(source.get("company") or tender_type).upper(),
                approval_code=source.get("transaction_url") and "APPROVED" or body.get("id"),
                rrn=source.get("reference_number"),
                gateway_ref=body.get("id"),
                last4=source.get("number", "")[-4:] or None,
                token=token,
            )
        return GatewayResult(
            approved=False,
            gateway=self.name,
            decline_reason=(source.get("message") or body.get("message") or status or "declined"),
        )

    async def refund(self, gateway_ref: str, amount: float) -> GatewayResult:
        import httpx

        amount_minor = int(round(amount * 100))
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{self._BASE_URL}/payments/{gateway_ref}/refund",
                    json={"amount": amount_minor},
                    auth=(self._api_key, ""),
                )
        except httpx.HTTPError as exc:
            raise PaymentDeclined(f"moyasar refund network error: {exc}", gateway=self.name)
        body = resp.json() if resp.content else {}
        ok = resp.status_code < 400 and (body.get("status") or "").lower() in ("refunded", "paid")
        return GatewayResult(
            approved=ok,
            gateway=self.name,
            gateway_ref=body.get("id") or gateway_ref,
            decline_reason=None if ok else (body.get("message") or "refund_failed"),
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------
def get_gateway() -> PaymentGateway:
    """Return the active gateway: Moyasar when configured, else the sandbox.

    Selection is by ``MOYASAR_API_KEY`` presence. Per-client gateway accounts
    (``payment_accounts``, PAY-06) are a later refinement; today the platform key
    drives the single online gateway and the sandbox is the safe default.
    """
    api_key = getattr(settings, "moyasar_api_key", "") or ""
    if api_key:
        logger.debug("Resolved Moyasar payment gateway from MOYASAR_API_KEY")
        return MoyasarGateway(api_key)
    return SandboxGateway()
