import json
from typing import Optional, Any, List

from dependencies.features import FEATURE_KEYS


# ------------------ MA-07 feature-entitlement tier helpers ------------------
# The generic packages CRUD scaffold (PackagesService + /api/v1/entities/packages)
# was removed as an orphaned, write-unauthenticated duplicate (H1). The only
# package surface is the master-gated soft-delete path in routers/features.py;
# these two helpers are the part of this module it (and tenant.py) still depend on.
def normalize_feature_tier(value: Any) -> Optional[str]:
    """Validate + JSON-serialize a package feature tier for storage.

    ``value`` is the list of ENABLED feature keys the package unlocks, or ``None``
    for "no tier" (the package does not restrict features). Returns a canonical
    JSON string (deduped, sorted) or ``None``. Raises ``ValueError`` on a key
    outside ``FEATURE_KEYS`` so an invalid tier is rejected at the boundary rather
    than silently stored.
    """
    if value is None:
        return None
    if isinstance(value, str):  # already serialized (defensive)
        return value
    unknown = sorted({f for f in value if f not in FEATURE_KEYS})
    if unknown:
        raise ValueError(f"Unknown feature keys: {', '.join(unknown)}")
    chosen = set(value)
    return json.dumps([k for k in sorted(FEATURE_KEYS) if k in chosen])


def parse_feature_tier(raw: Any) -> Optional[List[str]]:
    """Parse a package's stored feature tier into a list of enabled keys, or None.

    ``None`` means the package defines no tier (do not restrict). A malformed
    stored value degrades to ``None`` rather than raising.
    """
    if not raw:
        return None
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, list) else None
