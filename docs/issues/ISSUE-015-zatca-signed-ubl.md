# ISSUE-015 — ZATCA: produce a valid signed UBL (XAdES + C14N + persisted UUID)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** C2 · **Stories:** 16, 17, 18

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Today the computed ECDSA stamp is stored on the row + QR TLV but never injected into the XML, so the document POSTed to Fatoora is **unsigned**; the hash is also computed over a non-canonicalized string, and the invoice UUID is never persisted (submission sends `uuid=""`). Make the signing path produce a gateway-valid document:
- Build an enveloped XAdES signature in `<ext:UBLExtensions>` (SignedProperties + `ds:Signature` with the ECDSA value + cert) and inject it before submission.
- Canonicalize (C14N) the UBL before hashing so the gateway's recomputed hash matches.
- Persist `ZatcaDocuments.invoice_uuid` at generation time and emit it as `cbc:UUID`.

## Acceptance criteria
- [ ] The submitted `signed_xml` contains a `ds:Signature` inside `UBLExtensions` (not the plain UBL).
- [ ] The invoice hash is computed over C14N output.
- [ ] `cbc:UUID` is non-empty and equals the persisted `invoice_uuid`.
- [ ] Tests assert signature-present, UUID non-empty/persisted, and hash-over-C14N (specific facts, not a full-XML snapshot).

## Blocked by
- ISSUE-014 (the per-client PIH feeds the signed document)
