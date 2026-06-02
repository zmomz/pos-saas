"""ZATCA Phase-2 (Fatoora) e-invoicing: real cryptography + onboarding client.

Phase A left ZATCA as a QR + sequencing *skeleton* with a placeholder HMAC
"stamp" (`services/production.py::ZATCAService.generate_cryptographic_stamp`).
That is not a valid CSID/ECDSA signature and is a legal blocker for any KSA
go-live. This module implements the compliance-critical primitives for real:

* **EC keypair + CSR** — secp256k1 private key and a PKCS#10 CSR built from the
  ZATCA EGS (E-invoice Generation Solution) template: the required subject
  (CN/OU/O/C), the EGS `subjectAltName` directory (serial, VAT/UID, invoice
  type, address, business category), and the ZATCA certificate-template-name
  extension. This is the artifact submitted to Fatoora during onboarding.
* **Real cryptographic stamp** — ECDSA-over-SHA256 signature of the canonical
  invoice hash using the EGS private key. Verifiable with the public key;
  replaces the HMAC placeholder.
* **Secrets at rest** — AES-256-GCM (`encrypt_secret`/`decrypt_secret`) so the
  private key, ZATCA-issued secret and CSID are never stored in clear text.
* **Invoice hash + PIH** — base64 SHA-256 of the canonical XML and the
  hash-chain seed (`INITIAL_PIH`) used to chain invoices per ZATCA §QR/hash.
* **Fatoora API client** — compliance CSID, production CSID, and
  reporting/clearance calls, with a sandbox / simulation / production switch.

Network calls require ``ZATCA_API_BASE_URL`` (or a recognised
``ZATCA_ENVIRONMENT``) to be set; otherwise callers surface a 503 — the same
honest "stub until configured" contract used for Stripe/SMTP in Phase A. All
cryptography here works fully offline (no network, no external SDK).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any, Dict, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509 import (
    CertificateSigningRequestBuilder,
    DirectoryName,
    Name,
    NameAttribute,
    ObjectIdentifier,
    SubjectAlternativeName,
    UnrecognizedExtension,
    load_pem_x509_csr,
)
from cryptography.x509.oid import NameOID

from core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment / endpoint resolution
# ---------------------------------------------------------------------------
# ZATCA exposes three Fatoora gateways. "sandbox" is the developer-portal used
# for the compliance simulation, "simulation" the pre-production gateway, and
# "core" the live production gateway.
ENV_BASE_URLS: Dict[str, str] = {
    "sandbox": "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal",
    "simulation": "https://gw-fatoora.zatca.gov.sa/e-invoicing/simulation",
    "production": "https://gw-fatoora.zatca.gov.sa/e-invoicing/core",
}

# Certificate-template-name carried in the ZATCA CSR custom extension. The value
# differs per environment so ZATCA routes the CSID to the right authority.
ENV_CSR_TEMPLATE: Dict[str, str] = {
    "sandbox": "TSTZATCA-Code-Signing",
    "simulation": "PREZATCA-Code-Signing",
    "production": "ZATCA-Code-Signing",
}

# Microsoft certificate-template-name OID, reused verbatim by the ZATCA EGS spec.
_CSR_TEMPLATE_OID = ObjectIdentifier("1.3.6.1.4.1.311.20.2")
# userid / UID (carries the 15-digit VAT registration number in the EGS SAN).
_UID_OID = ObjectIdentifier("0.9.2342.19200300.100.1.1")
# registeredAddress.
_REGISTERED_ADDRESS_OID = ObjectIdentifier("2.5.4.26")

# PIH (Previous Invoice Hash) seed for the first invoice in a chain: base64 of
# SHA-256("0"), per ZATCA hash-chaining rules.
INITIAL_PIH: str = base64.b64encode(hashlib.sha256(b"0").digest()).decode()


def normalize_environment(value: Optional[str]) -> str:
    env = (value or getattr(settings, "zatca_environment", None) or "sandbox").lower()
    return env if env in ENV_BASE_URLS else "sandbox"


def resolve_base_url(environment: Optional[str] = None) -> Optional[str]:
    """Resolve the Fatoora gateway base URL, or ``None`` if not configured.

    Live network calls require an explicit operator opt-in so we never silently
    transmit invoices to a government gateway (and tests never hit the network):

    * an explicit ``ZATCA_API_BASE_URL`` always wins (e.g. a local mock), else
    * when ``ZATCA_ENVIRONMENT`` is set in the environment, the matching
      published Fatoora gateway URL is used.

    With neither set the integration is "not configured" and routers fail closed
    with a 503 — the same contract as Stripe/SMTP in Phase A.
    """
    override = getattr(settings, "zatca_api_base_url", None)
    if override:
        return override.rstrip("/")
    if "ZATCA_ENVIRONMENT" in os.environ:
        return ENV_BASE_URLS.get(normalize_environment(environment))
    return None


# ---------------------------------------------------------------------------
# Secrets at rest — AES-256-GCM
# ---------------------------------------------------------------------------
def _aes_key() -> bytes:
    """Derive a 32-byte AES-256 key.

    Prefers ``ZATCA_ENCRYPTION_KEY``; falls back to the JWT secret so the
    feature works out-of-the-box in dev. Production deployments MUST set a
    dedicated key — losing it makes stored CSIDs/keys unrecoverable.
    """
    raw = getattr(settings, "zatca_encryption_key", None) or settings.jwt_secret_key
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    """AES-256-GCM encrypt and base64-encode ``nonce || ciphertext||tag``."""
    nonce = os.urandom(12)
    ct = AESGCM(_aes_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Inverse of :func:`encrypt_secret`. Raises on tamper/wrong key."""
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(_aes_key()).decrypt(nonce, ct, None).decode("utf-8")


# ---------------------------------------------------------------------------
# EC keypair + CSR (EGS onboarding artifact)
# ---------------------------------------------------------------------------
def _der_utf8_string(value: str) -> bytes:
    """Minimal DER encoding of an ASN.1 UTF8String (tag 0x0C). Lengths here are
    always < 128, so single-byte length encoding is sufficient."""
    body = value.encode("utf-8")
    return bytes([0x0C, len(body)]) + body


def generate_egs_keypair_and_csr(
    *,
    common_name: str,
    organization_name: str,
    organization_unit: str,
    vat_number: str,
    egs_serial: str,
    invoice_type: str = "1100",
    location_address: str = "Riyadh",
    business_category: str = "retail",
    country: str = "SA",
    environment: Optional[str] = None,
) -> Tuple[str, str]:
    """Generate an EC secp256k1 private key and a ZATCA-EGS PKCS#10 CSR.

    Returns ``(private_key_pem, csr_pem)``. The CSR is a genuine PKCS#10 request
    (parseable/verifiable with OpenSSL) carrying the subject, the EGS
    ``subjectAltName`` directory and the certificate-template-name extension
    that ZATCA's onboarding flow requires.

    ``egs_serial`` follows the ZATCA format ``1-<solution>|2-<model>|3-<sn>``.
    """
    env = normalize_environment(environment)
    private_key = ec.generate_private_key(ec.SECP256K1())

    subject = Name([
        NameAttribute(NameOID.COMMON_NAME, common_name),
        NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organization_unit),
        NameAttribute(NameOID.ORGANIZATION_NAME, organization_name),
        NameAttribute(NameOID.COUNTRY_NAME, country),
    ])

    egs_directory = DirectoryName(Name([
        NameAttribute(NameOID.SERIAL_NUMBER, egs_serial),
        NameAttribute(_UID_OID, vat_number),
        NameAttribute(NameOID.TITLE, invoice_type),
        NameAttribute(_REGISTERED_ADDRESS_OID, location_address),
        NameAttribute(NameOID.BUSINESS_CATEGORY, business_category),
    ]))

    template_ext = UnrecognizedExtension(
        _CSR_TEMPLATE_OID, _der_utf8_string(ENV_CSR_TEMPLATE[env])
    )

    csr = (
        CertificateSigningRequestBuilder()
        .subject_name(subject)
        .add_extension(SubjectAlternativeName([egs_directory]), critical=False)
        .add_extension(template_ext, critical=False)
        .sign(private_key, hashes.SHA256())
    )

    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return key_pem, csr_pem


def csr_to_base64(csr_pem: str) -> str:
    """ZATCA accepts the CSR as a base64-encoded PEM string."""
    return base64.b64encode(csr_pem.encode("utf-8")).decode("ascii")


def public_key_pem_from_private(private_key_pem: str) -> str:
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def is_valid_csr(csr_pem: str) -> bool:
    try:
        load_pem_x509_csr(csr_pem.encode("utf-8"))
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Invoice hash + cryptographic stamp (ECDSA-SHA256)
# ---------------------------------------------------------------------------
def invoice_hash_b64(canonical_xml: bytes) -> str:
    """ZATCA invoice hash: base64 of the SHA-256 digest of the canonical XML."""
    return base64.b64encode(hashlib.sha256(canonical_xml).digest()).decode("ascii")


def sign_invoice_hash(private_key_pem: str, invoice_hash_base64: str) -> str:
    """Produce the cryptographic stamp: ECDSA-SHA256 over the invoice hash.

    The 32-byte SHA-256 digest (decoded from ``invoice_hash_base64``) is signed
    with the EGS private key. Returns the base64-encoded DER signature. This is
    a real, verifiable signature — not the previous HMAC placeholder.
    """
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    digest = base64.b64decode(invoice_hash_base64)
    signature = key.sign(digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    return base64.b64encode(signature).decode("ascii")


def verify_stamp(public_key_pem: str, invoice_hash_base64: str, stamp_b64: str) -> bool:
    """Verify a stamp produced by :func:`sign_invoice_hash`."""
    pub = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    digest = base64.b64decode(invoice_hash_base64)
    try:
        pub.verify(
            base64.b64decode(stamp_b64),
            digest,
            ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------------------
# Fatoora API client (compliance / production CSID, reporting / clearance)
# ---------------------------------------------------------------------------
class ZatcaApiError(Exception):
    """Raised when a Fatoora gateway call fails or is not configured."""

    def __init__(self, message: str, *, status_code: Optional[int] = None,
                 error_type: str = "api"):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class ZatcaApiClient:
    """Thin async client over the Fatoora REST gateway.

    Construct with :meth:`from_settings` so an unconfigured integration raises
    a clear ``ZatcaApiError`` that the router maps to 503.
    """

    # ZATCA pins the API version via this header.
    _VERSION = "V2"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_settings(cls, environment: Optional[str] = None) -> "ZatcaApiClient":
        base = resolve_base_url(environment)
        if not base:
            raise ZatcaApiError(
                "ZATCA gateway is not configured. Set ZATCA_API_BASE_URL or a "
                "recognised ZATCA_ENVIRONMENT (sandbox/simulation/production).",
                status_code=503,
                error_type="not_configured",
            )
        return cls(base)

    async def _post(self, path: str, *, json: Dict[str, Any],
                    headers: Dict[str, str]) -> Dict[str, Any]:
        import httpx  # local import keeps module import cheap

        url = f"{self.base_url}{path}"
        base_headers = {
            "Accept-Version": self._VERSION,
            "Accept-Language": "en",
            "Content-Type": "application/json",
        }
        base_headers.update(headers)
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(url, json=json, headers=base_headers)
        except httpx.HTTPError as exc:  # network-level failure
            raise ZatcaApiError(f"ZATCA gateway unreachable: {exc}",
                                status_code=502, error_type="network") from exc
        if resp.status_code >= 400:
            raise ZatcaApiError(
                f"ZATCA gateway returned {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code, error_type="gateway",
            )
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    async def request_compliance_csid(self, csr_pem: str, otp: str) -> Dict[str, Any]:
        """Exchange the CSR + OTP for a compliance CSID (binarySecurityToken)."""
        return await self._post(
            "/compliance",
            json={"csr": csr_to_base64(csr_pem)},
            headers={"OTP": otp},
        )

    async def request_production_csid(
        self, compliance_request_id: str, token: str, secret: str
    ) -> Dict[str, Any]:
        """Exchange the compliance CSID for a production CSID."""
        return await self._post(
            "/production/csids",
            json={"compliance_request_id": compliance_request_id},
            headers={"Authorization": _basic_auth(token, secret)},
        )

    async def submit_invoice(
        self, *, signed_xml: str, invoice_hash: str, invoice_uuid: str,
        token: str, secret: str, clearance: bool = False,
    ) -> Dict[str, Any]:
        """Submit a signed invoice for reporting (simplified) or clearance
        (standard). ZATCA requires clearance within 24h for standard invoices."""
        path = (
            "/invoices/clearance/single" if clearance
            else "/invoices/reporting/single"
        )
        headers = {"Authorization": _basic_auth(token, secret)}
        if clearance:
            headers["Clearance-Status"] = "1"
        return await self._post(
            path,
            json={
                "invoiceHash": invoice_hash,
                "uuid": invoice_uuid,
                "invoice": base64.b64encode(signed_xml.encode("utf-8")).decode("ascii"),
            },
            headers=headers,
        )


def _basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"
