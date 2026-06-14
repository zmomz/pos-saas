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


def canonicalize_invoice_xml(xml: str) -> bytes:
    """C14N (REC-xml-c14n-20010315) serialization of the UBL invoice, as bytes.

    ZATCA recomputes the invoice hash on its side and compares it to the
    submitted value, so the hash MUST be taken over the *canonical* form — not
    the raw string the generator happened to emit. Canonicalization erases
    insignificant differences (namespace-declaration order, attribute order,
    empty-element form) that would otherwise make the gateway's recomputed digest
    diverge from ours and reject the document. Hashing the raw string — what the
    pre-fix path did — is exactly that latent divergence.
    """
    from xml.etree.ElementTree import canonicalize

    return canonicalize(xml_data=xml).encode("utf-8")


# ---------------------------------------------------------------------------
# Enveloped XAdES signature (ds:Signature in ext:UBLExtensions)
# ---------------------------------------------------------------------------
# XML-DSig / XAdES / UBL signature namespaces, per the ZATCA Phase-2 spec.
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"
UBL_EXT_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
UBL_SIG_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2"
UBL_SAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2"
UBL_SBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2"
_CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

_C14N_ALGO = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
_SHA256_ALGO = "http://www.w3.org/2001/04/xmlenc#sha256"
_ECDSA_SHA256_ALGO = "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"
_ENVELOPED_ALGO = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

# Stable, human-readable prefixes for the spliced signature block (ElementTree
# otherwise emits ns0/ns1…). Process-global but idempotent and serialization-only.
def _register_signature_prefixes() -> None:
    from xml.etree.ElementTree import register_namespace

    for prefix, uri in (
        ("ext", UBL_EXT_NS),
        ("sig", UBL_SIG_NS),
        ("sac", UBL_SAC_NS),
        ("sbc", UBL_SBC_NS),
        ("ds", DS_NS),
        ("xades", XADES_NS),
        ("cbc", _CBC_NS),
    ):
        register_namespace(prefix, uri)


_register_signature_prefixes()


def _c14n_digest_b64(element) -> str:
    """SHA-256 (base64) of the C14N serialization of an ElementTree element."""
    from xml.etree.ElementTree import canonicalize, tostring

    canonical = canonicalize(xml_data=tostring(element, encoding="unicode"))
    return base64.b64encode(hashlib.sha256(canonical.encode("utf-8")).digest()).decode("ascii")


def _self_signed_certificate(private_key, signing_time):
    """A self-signed X509 cert from the EGS key, used when no production CSID is
    issued yet (local-only signing). The signature still carries a real cert so
    its KeyInfo/SigningCertificate structure is well-formed."""
    from datetime import timedelta

    from cryptography import x509
    from cryptography.x509.oid import NameOID

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "POS EGS")])
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(signing_time)
        .not_valid_after(signing_time + timedelta(days=365 * 5))
        .sign(private_key, hashes.SHA256())
    )


def _resolve_certificate(private_key, certificate_b64, signing_time):
    """Load the issued ZATCA cert (production CSID, base64 DER or PEM) when
    present, else mint a self-signed cert from the EGS key."""
    from cryptography import x509

    if certificate_b64:
        der = base64.b64decode(certificate_b64)
        try:
            return x509.load_der_x509_certificate(der)
        except ValueError:
            return x509.load_pem_x509_certificate(der)
    return _self_signed_certificate(private_key, signing_time)


def build_signed_xml(
    *,
    unsigned_xml: str,
    private_key_pem: str,
    invoice_hash_b64: str,
    signing_time,
    certificate_b64: Optional[str] = None,
) -> str:
    """Inject an enveloped XAdES ``ds:Signature`` into the UBL invoice.

    The plain UBL is what the pre-fix path stored and submitted, so Fatoora
    received an *unsigned* document. This builds the ZATCA signature structure —
    a ``ds:Signature`` (SignedInfo referencing the invoice digest + the XAdES
    SignedProperties, the ECDSA SignatureValue over the canonical SignedInfo, and
    a KeyInfo carrying the signing cert) wrapped in
    ``ext:UBLExtensions/.../sac:SignatureInformation`` — and splices it in as the
    Invoice's first child. The invoice body is left byte-for-byte intact so the
    hash already taken over it (``invoice_hash_b64``, computed over C14N) stays
    the document's authoritative digest, and the PIH chain element is untouched.

    ``signing_time`` is a timezone-aware datetime; ``certificate_b64`` is the
    issued production CSID when onboarded, else a self-signed cert is minted.
    """
    import xml.etree.ElementTree as ET
    from cryptography.hazmat.primitives import serialization

    DS = f"{{{DS_NS}}}"
    XADES = f"{{{XADES_NS}}}"
    EXT = f"{{{UBL_EXT_NS}}}"
    SIG = f"{{{UBL_SIG_NS}}}"
    SAC = f"{{{UBL_SAC_NS}}}"
    SBC = f"{{{UBL_SBC_NS}}}"
    CBC = f"{{{_CBC_NS}}}"

    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    cert = _resolve_certificate(private_key, certificate_b64, signing_time)
    cert_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")
    cert_digest = base64.b64encode(hashlib.sha256(cert_b64.encode("utf-8")).digest()).decode("ascii")
    signing_time_str = signing_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # XAdES SignedProperties — signing time + the signing-certificate reference.
    signed_props = ET.Element(XADES + "SignedProperties")
    signed_props.set("Id", "xadesSignedProperties")
    ssp = ET.SubElement(signed_props, XADES + "SignedSignatureProperties")
    ET.SubElement(ssp, XADES + "SigningTime").text = signing_time_str
    cert_el = ET.SubElement(ET.SubElement(ssp, XADES + "SigningCertificate"), XADES + "Cert")
    cert_digest_el = ET.SubElement(cert_el, XADES + "CertDigest")
    ET.SubElement(cert_digest_el, DS + "DigestMethod").set("Algorithm", _SHA256_ALGO)
    ET.SubElement(cert_digest_el, DS + "DigestValue").text = cert_digest
    issuer_serial = ET.SubElement(cert_el, XADES + "IssuerSerial")
    ET.SubElement(issuer_serial, DS + "X509IssuerName").text = cert.issuer.rfc4514_string()
    ET.SubElement(issuer_serial, DS + "X509SerialNumber").text = str(cert.serial_number)
    signed_props_digest = _c14n_digest_b64(signed_props)

    # SignedInfo — reference #1 is the invoice (digest = the C14N invoice hash),
    # reference #2 binds the XAdES SignedProperties.
    signed_info = ET.Element(DS + "SignedInfo")
    ET.SubElement(signed_info, DS + "CanonicalizationMethod").set("Algorithm", _C14N_ALGO)
    ET.SubElement(signed_info, DS + "SignatureMethod").set("Algorithm", _ECDSA_SHA256_ALGO)
    inv_ref = ET.SubElement(signed_info, DS + "Reference")
    inv_ref.set("Id", "invoiceSignedData")
    inv_ref.set("URI", "")
    transforms = ET.SubElement(inv_ref, DS + "Transforms")
    ET.SubElement(transforms, DS + "Transform").set("Algorithm", _ENVELOPED_ALGO)
    ET.SubElement(transforms, DS + "Transform").set("Algorithm", _C14N_ALGO)
    ET.SubElement(inv_ref, DS + "DigestMethod").set("Algorithm", _SHA256_ALGO)
    ET.SubElement(inv_ref, DS + "DigestValue").text = invoice_hash_b64
    sp_ref = ET.SubElement(signed_info, DS + "Reference")
    sp_ref.set("Type", "http://uri.etsi.org/01903#SignedProperties")
    sp_ref.set("URI", "#xadesSignedProperties")
    ET.SubElement(sp_ref, DS + "DigestMethod").set("Algorithm", _SHA256_ALGO)
    ET.SubElement(sp_ref, DS + "DigestValue").text = signed_props_digest

    # SignatureValue — ECDSA-SHA256 over the canonical SignedInfo.
    canonical_signed_info = ET.canonicalize(xml_data=ET.tostring(signed_info, encoding="unicode"))
    signature_value = base64.b64encode(
        private_key.sign(canonical_signed_info.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    ).decode("ascii")

    # ds:Signature
    signature = ET.Element(DS + "Signature")
    signature.set("Id", "signature")
    signature.append(signed_info)
    ET.SubElement(signature, DS + "SignatureValue").text = signature_value
    x509_data = ET.SubElement(ET.SubElement(signature, DS + "KeyInfo"), DS + "X509Data")
    ET.SubElement(x509_data, DS + "X509Certificate").text = cert_b64
    qualifying = ET.SubElement(ET.SubElement(signature, DS + "Object"), XADES + "QualifyingProperties")
    qualifying.set("Target", "signature")
    qualifying.append(signed_props)

    # UBL signature wrapper
    ubl_exts = ET.Element(EXT + "UBLExtensions")
    extension = ET.SubElement(ubl_exts, EXT + "UBLExtension")
    content = ET.SubElement(extension, EXT + "ExtensionContent")
    ubl_sigs = ET.SubElement(content, SIG + "UBLDocumentSignatures")
    sig_info = ET.SubElement(ubl_sigs, SAC + "SignatureInformation")
    ET.SubElement(sig_info, CBC + "ID").text = "urn:oasis:names:specification:ubl:signature:1"
    ET.SubElement(sig_info, SBC + "ReferencedSignatureID").text = (
        "urn:oasis:names:specification:ubl:signature:Invoice"
    )
    sig_info.append(signature)

    ext_block = ET.tostring(ubl_exts, encoding="unicode")

    # Splice the signature block in as the Invoice's first child, leaving the
    # invoice body byte-for-byte intact (so its C14N hash is unchanged).
    start = unsigned_xml.index("<Invoice")
    insert_at = unsigned_xml.index(">", start) + 1
    return unsigned_xml[:insert_at] + ext_block + unsigned_xml[insert_at:]


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


def public_key_der_b64(private_key_pem: str) -> str:
    """Base64 of the DER ``SubjectPublicKeyInfo`` (TLV tag 8 carries these bytes)."""
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    der = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(der).decode("ascii")


# ---------------------------------------------------------------------------
# ZATCA QR — stamped TLV (tags 1-8) + PNG rendering
# ---------------------------------------------------------------------------
def _ber_length(n: int) -> bytes:
    """BER definite-length encoding (TLV length octets)."""
    if n < 0x80:
        return bytes([n])
    out = bytearray()
    while n:
        out.insert(0, n & 0xFF)
        n >>= 8
    return bytes([0x80 | len(out)]) + bytes(out)


def _tlv_field(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _ber_length(len(value)) + value


def build_stamped_qr_tlv(
    *,
    seller_name: str,
    vat_number: str,
    timestamp: str,
    total_with_vat: str,
    vat_amount: str,
    invoice_hash_b64: str,
    stamp_b64: str,
    public_key_der_base64: str,
) -> str:
    """Build the ZATCA Phase-2 **stamped** QR payload (base64 TLV, tags 1-8).

    Tags 1-5 are the human-readable invoice fields (Phase-1 QR); tags 6-8 add the
    cryptographic stamp that makes the QR Phase-2 compliant:

      6 = invoice hash (base64 SHA-256 of the canonical XML)
      7 = ECDSA signature (the cryptographic stamp)
      8 = EGS public key (DER ``SubjectPublicKeyInfo``)

    Strings are UTF-8; the binary tags carry the decoded bytes of their base64
    inputs. Returns the base64 of the concatenated TLV — exactly what the QR image
    encodes and what tag-6 readers re-hash to verify the invoice.
    """
    payload = bytearray()
    payload += _tlv_field(1, seller_name.encode("utf-8"))
    payload += _tlv_field(2, vat_number.encode("utf-8"))
    payload += _tlv_field(3, timestamp.encode("utf-8"))
    payload += _tlv_field(4, total_with_vat.encode("utf-8"))
    payload += _tlv_field(5, vat_amount.encode("utf-8"))
    payload += _tlv_field(6, base64.b64decode(invoice_hash_b64))
    payload += _tlv_field(7, base64.b64decode(stamp_b64))
    payload += _tlv_field(8, base64.b64decode(public_key_der_base64))
    return base64.b64encode(bytes(payload)).decode("ascii")


def parse_tlv_tags(tlv_b64: str) -> Dict[int, bytes]:
    """Decode a base64 TLV payload into ``{tag: value_bytes}`` (test/verification)."""
    raw = base64.b64decode(tlv_b64)
    out: Dict[int, bytes] = {}
    i = 0
    while i < len(raw):
        tag = raw[i]
        i += 1
        length = raw[i]
        i += 1
        if length & 0x80:
            num = length & 0x7F
            length = int.from_bytes(raw[i:i + num], "big")
            i += num
        out[tag] = raw[i:i + length]
        i += length
    return out


def render_qr_png_base64(tlv_b64: str) -> str:
    """Render the QR TLV payload to a base64 PNG (``data:image/png;base64,`` body).

    Server-side rendering (C-4): the frontend receives a ready-to-show PNG and
    does not need a QR library. The QR encodes the base64 TLV string verbatim.
    """
    import io

    import qrcode

    img = qrcode.make(tlv_b64)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


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
