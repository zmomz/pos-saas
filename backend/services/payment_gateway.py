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
Tap/HyperPay/PayTabs slot in behind this same interface later. In-store SoftPOS
terminal capture is :class:`GeideaTerminalGateway` (PAY-05/HW-03, F-005) — the
amount is pushed to a paired Geidea SoftPOS terminal which prompts the customer to
tap and returns a real approval/RRN/network (or a decline that blocks the sale).
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
    # Prepaid store credit (CRM-03/PRC-05, F-038). Settles internally against the
    # gift card's balance — no gateway round-trip — but has a DB side effect (the
    # card balance is decremented atomically in the sale), handled on the sale path.
    "giftcard",
)

# Tenders that must capture a real gateway approval before the sale can complete.
# cash is physical, transfer is settled out-of-band, loyalty and giftcard are
# internal ledger moves — none of those route to a gateway.
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
        # An omnichannel online order (Salla/Zid, F-046) is paid + settled in the
        # external store, not on our gateway — record it as an out-of-band transfer.
        "online": "transfer",
        "apple_pay": "applepay",
        "stc_pay": "stcpay",
        "stcpay": "stcpay",
        "credit": "card",
        "debit": "card",
        # Gift card / store credit (F-038).
        "gift_card": "giftcard",
        "giftcard": "giftcard",
        "store_credit": "giftcard",
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
# In-store SoftPOS terminal capture (PAY-05 / HW-03, F-005)
# ---------------------------------------------------------------------------
# The terminal providers the POS can push a card-like tender to. Geidea SoftPOS
# is the first (operator-selected) in-store provider; PAX/Urovo/N-Genius slot in
# behind the same :class:`GeideaTerminalGateway`-shaped interface later.
TERMINAL_PROVIDERS: tuple[str, ...] = ("geidea",)


class GeideaTerminalGateway(PaymentGateway):
    """In-store SoftPOS terminal capture via **Geidea** (PAY-05 / HW-03, F-005).

    Unlike the online gateways (Moyasar), an in-store capture is initiated against
    a *paired* SoftPOS terminal: the POS pushes ``{terminal, amount}`` to Geidea,
    the customer taps their Mada/Apple Pay card on the device, and the device
    returns a real approval (network + approval code + RRN) or a decline. A decline
    raises :class:`PaymentDeclined`, which rolls the whole sale back (PAY-05).

    Two modes, selected by credentials (mirrors Moyasar's "implemented but inactive
    until a live key is set"):

    * **sandbox** (default, no ``GEIDEA_API_KEY``): a deterministic, hardware-free
      simulation so the in-store flow is demonstrable on any install (OPS-08).
      Approves by default; ``simulate="decline"`` forces a terminal decline. It
      reports ``gateway="geidea"`` so a refund routes back through this same
      adapter (refund-to-origin, F-004).
    * **live** (``GEIDEA_API_KEY`` set + a paired terminal serial): a real
      server→Geidea capture. NOTE: this needs live Geidea merchant credentials and
      a physically paired SoftPOS device — an operator/hardware step flagged in the
      hand-off; until then the sandbox path runs.
    """

    name = "geidea"
    _BASE_URL = "https://api.merchant.geidea.net/pgw/api/v1"

    def __init__(self, api_key: Optional[str] = None, *, terminal_serial: Optional[str] = None):
        self._api_key = api_key or ""
        self._terminal_serial = terminal_serial

    @property
    def live(self) -> bool:
        """True once real Geidea credentials are configured."""
        return bool(self._api_key)

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
        if not self.live:
            # Hardware-free sandbox simulation (OPS-08). A real capture activates
            # once GEIDEA_API_KEY + a paired terminal exist.
            if (simulate or "").strip().lower() == "decline":
                return GatewayResult(
                    approved=False,
                    gateway=self.name,
                    decline_reason="terminal_declined",
                )
            ref = uuid.uuid4().hex
            return GatewayResult(
                approved=True,
                gateway=self.name,
                # SoftPOS is Mada-first in KSA; honour an explicit wallet network.
                network=_SANDBOX_NETWORK.get(tender_type, "MADA"),
                approval_code=ref[:6].upper(),
                rrn=ref[6:18],
                gateway_ref=f"geidea_sbx_{ref}",
                last4=ref[-4:],
                token=f"tok_geidea_{ref[:16]}",
            )

        # ---- live capture against the paired Geidea SoftPOS terminal ----
        import httpx  # local import keeps module import cheap

        amount_minor = int(round(amount * 100))
        payload = {
            "amount": amount_minor,
            "currency": currency,
            "terminalSerial": (metadata or {}).get("terminal_serial") or self._terminal_serial,
            "captureMethod": "terminal",
            "merchantReferenceId": (metadata or {}).get("reference"),
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.post(
                    f"{self._BASE_URL}/terminal/charge",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:  # network/terminal unreachable
            raise PaymentDeclined(f"geidea terminal error: {exc}", gateway=self.name)

        if resp.status_code >= 500:
            raise PaymentDeclined(
                f"geidea server error {resp.status_code}", gateway=self.name
            )
        body = resp.json() if resp.content else {}
        status = (body.get("status") or "").lower()
        if status in ("approved", "captured", "success"):
            return GatewayResult(
                approved=True,
                gateway=self.name,
                network=(body.get("network") or tender_type).upper(),
                approval_code=body.get("approvalCode") or body.get("authCode"),
                rrn=body.get("rrn") or body.get("retrievalReferenceNumber"),
                gateway_ref=body.get("transactionId") or body.get("id"),
                last4=(body.get("maskedPan") or "")[-4:] or None,
                token=body.get("cardToken"),
            )
        return GatewayResult(
            approved=False,
            gateway=self.name,
            decline_reason=(body.get("detailedResponseMessage") or status or "declined"),
        )

    async def refund(self, gateway_ref: str, amount: float) -> GatewayResult:
        if not self.live:
            ref = uuid.uuid4().hex
            return GatewayResult(
                approved=True,
                gateway=self.name,
                gateway_ref=f"rfnd_{ref}",
                approval_code=ref[:6].upper(),
            )
        import httpx

        amount_minor = int(round(amount * 100))
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.post(
                    f"{self._BASE_URL}/terminal/refund",
                    json={"transactionId": gateway_ref, "amount": amount_minor},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            raise PaymentDeclined(f"geidea refund error: {exc}", gateway=self.name)
        body = resp.json() if resp.content else {}
        ok = resp.status_code < 400 and (body.get("status") or "").lower() in (
            "refunded",
            "approved",
            "success",
        )
        return GatewayResult(
            approved=ok,
            gateway=self.name,
            gateway_ref=body.get("transactionId") or gateway_ref,
            decline_reason=None if ok else (body.get("detailedResponseMessage") or "refund_failed"),
        )


def get_terminal_gateway(provider: str = "geidea") -> GeideaTerminalGateway:
    """Resolve the in-store terminal gateway for ``provider`` (PAY-05/HW-03).

    Today only Geidea SoftPOS is wired (the operator's choice). It runs live once
    ``GEIDEA_API_KEY`` is configured, otherwise as the deterministic sandbox so the
    terminal flow is demonstrable without hardware.
    """
    api_key = getattr(settings, "geidea_api_key", "") or ""
    terminal_serial = getattr(settings, "geidea_terminal_serial", "") or None
    if (provider or "geidea").strip().lower() != "geidea":
        # Unknown provider — fall back to the sandbox Geidea adapter so the capture
        # path still works rather than dead-ending.
        return GeideaTerminalGateway()
    return GeideaTerminalGateway(api_key, terminal_serial=terminal_serial)


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


def get_gateway_for(gateway_name: Optional[str]) -> PaymentGateway:
    """Resolve the gateway that should **reverse** a tender captured by ``gateway_name``.

    Refund-to-origin (PAY-10, F-004) must route back through the same provider that
    captured the charge — a sandbox-captured tender reverses via the sandbox even if
    a live key is later configured, and a Moyasar-captured tender reverses via
    Moyasar (raising :class:`GatewayNotConfigured` if the key is now absent, so the
    operator is told the reversal could not be processed online).
    """
    name = (gateway_name or "").strip().lower()
    if name == "sandbox":
        return SandboxGateway()
    if name == "geidea":
        # In-store terminal refund (HW-03): reverse through the same SoftPOS
        # adapter, live or sandbox per current credentials.
        return get_terminal_gateway("geidea")
    if name == "moyasar":
        api_key = getattr(settings, "moyasar_api_key", "") or ""
        if api_key:
            return MoyasarGateway(api_key)
        raise GatewayNotConfigured(
            "Moyasar gateway not configured; cannot reverse a Moyasar tender online"
        )
    # Unknown/legacy capture gateway — fall back to the active gateway.
    return get_gateway()
