"""Shared, allowlist-bound filtering for client-supplied ``query_dict`` (SEC-17).

List endpoints accept a client JSON ``query`` (parsed into ``query_dict``) that
the generated services applied as ``Model.<field> == value`` for *any* column
the model happened to have (``hasattr(Model, field)``). That exposed an
unbounded filter surface — a client could filter on a sensitive column (e.g. a
webhook ``secret_key``) and use equality as a boolean oracle, or filter on
internal columns never meant to be queryable.

Each service now declares an explicit ``FILTERABLE_FIELDS`` allowlist and routes
client filters through :func:`apply_query_filters`, which applies only
allowlisted columns and silently ignores everything else (a disallowed field is
dropped, not 400'd, so legitimate clients sending an unknown key keep working).
"""
from typing import Any, Dict, Iterable, Optional, Tuple


def apply_query_filters(
    model: Any,
    query: Any,
    count_query: Any,
    query_dict: Optional[Dict[str, Any]],
    allowed_fields: Iterable[str],
) -> Tuple[Any, Any]:
    """Apply client equality filters to ``query``/``count_query``, allowlist-bound.

    Only keys that are BOTH in ``allowed_fields`` and real columns on ``model``
    are applied as ``model.<key> == value``; any other key is ignored. Returns
    the (possibly narrowed) ``(query, count_query)`` pair so callers keep their
    count consistent with the filtered selection.
    """
    if not query_dict:
        return query, count_query

    allowed = allowed_fields if isinstance(allowed_fields, (set, frozenset)) else set(allowed_fields or ())
    for field, value in query_dict.items():
        if field in allowed and hasattr(model, field):
            column = getattr(model, field)
            query = query.where(column == value)
            count_query = count_query.where(column == value)
    return query, count_query
