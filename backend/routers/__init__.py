# Routers package.
#
# ISSUE-009 — explicit router-registration allowlist.
#
# Router mounting is driven by this explicit list, NOT by blanket package
# discovery. `main.include_routers_from_package` imports and mounts a module
# ONLY if its short name appears here. This is the conscious-decision gate the
# §4 / theme-#1 audit asked for: the orphaned auto-CRUD scaffolds shipped live
# precisely because a `pkgutil.walk_packages` sweep auto-mounted every
# `routers/*.py` exposing `router`/`admin_router`. A newly-generated router now
# stays dark until someone adds it here and the registration test is updated.
#
# Keep this sorted and one-per-line so additions/removals are reviewable diffs.
# tests/test_router_registration.py asserts this list equals the set of router
# modules actually present in the package — so adding a router file without
# listing it (or listing one that no longer exists) fails CI.
REGISTERED_MODULES = (
    "admin_console",
    "aggregator",
    "api_usage",
    "audit_logs",
    "auth",
    "branches",
    "catalog",
    "categories",
    "customers",
    "discount_codes",
    "discounts",
    "expenses",
    "features",
    "gift_cards",
    "health",
    "loyalty_points",
    "loyalty_programs",
    "omnichannel",
    "payments_gateway",
    "pos",
    "printers",
    "product_variants",
    "production",
    "products",
    "promotions",
    "purchase_orders",
    "quotations",
    "receipt_templates",
    "restaurant",
    "staff_members",
    "stocktake",
    "storage",
    "store_settings",
    "suppliers",
    "tenant",
    "transactions",
    "user",
    "webhooks",
    "zatca",
)
