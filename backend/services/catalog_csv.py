"""ISSUE-064 — catalog CSV (de)serialization.

Pure, side-effect-free helpers that turn the product catalog into a CSV and
parse an uploaded CSV back into validated product dicts. The router owns the DB
upsert and tenancy; this module owns the column contract and per-row validation
so both can be unit-tested without a DB.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Tuple

# The canonical column contract. Export emits exactly these columns (in order);
# import accepts any subset but keys upserts off ``barcode``. ``name``/``price``
# are the only required fields on import.
CSV_COLUMNS: List[str] = [
    "name",
    "name_ar",
    "barcode",
    "category",
    "price",
    "cost_price",
    "quantity",
    "vat_rate",
    "is_active",
    "is_weighted",
    "is_open_price",
    "unit_label",
    "reorder_point",
    "reorder_quantity",
]

_FLOAT_FIELDS = {"price", "cost_price", "quantity", "vat_rate"}
_INT_FIELDS = {"reorder_point", "reorder_quantity"}
_BOOL_FIELDS = {"is_active", "is_weighted", "is_open_price"}
_TEXT_FIELDS = {"name", "name_ar", "barcode", "category", "unit_label"}

_TRUE = {"true", "1", "yes", "y"}
_FALSE = {"false", "0", "no", "n", ""}


def _cell(value: Any) -> str:
    """Render a model value into a CSV cell (None -> empty, bool -> true/false)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def products_to_csv(products) -> str:
    """Serialize an iterable of product rows into CSV text (header + rows)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for p in products:
        writer.writerow({col: _cell(getattr(p, col, None)) for col in CSV_COLUMNS})
    return buf.getvalue()


def parse_products_csv(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse CSV text into (valid_rows, errors).

    Each valid row is a typed dict ready for create/update. Each error is
    ``{"row": <1-based data row>, "errors": [<message>, ...]}`` — invalid rows
    are reported, never silently dropped.
    """
    reader = csv.DictReader(io.StringIO(text))
    valid: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, raw in enumerate(reader, start=1):
        row_errors: List[str] = []
        data: Dict[str, Any] = {}

        for col in CSV_COLUMNS:
            if col not in raw or raw[col] is None:
                continue
            value = raw[col].strip()
            if value == "" and col not in ("name",):
                continue  # blank optional cell -> leave field unset
            if col in _TEXT_FIELDS:
                data[col] = value
            elif col in _BOOL_FIELDS:
                low = value.lower()
                if low in _TRUE:
                    data[col] = True
                elif low in _FALSE:
                    data[col] = False
                else:
                    row_errors.append(f"{col}: '{value}' is not a boolean")
            elif col in _FLOAT_FIELDS:
                try:
                    data[col] = float(value)
                except ValueError:
                    row_errors.append(f"{col}: '{value}' is not a number")
            elif col in _INT_FIELDS:
                try:
                    data[col] = int(float(value))
                except ValueError:
                    row_errors.append(f"{col}: '{value}' is not an integer")

        # Required fields.
        if not data.get("name"):
            row_errors.append("name: required")
        if "price" not in data:
            row_errors.append("price: required")
        elif data["price"] < 0:
            row_errors.append("price: must be >= 0")

        if row_errors:
            errors.append({"row": idx, "errors": row_errors})
        else:
            valid.append(data)

    return valid, errors
