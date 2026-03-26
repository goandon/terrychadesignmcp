"""Product catalog DB adapter for terrychadesignmcp.

Author: Terry.Kim <goandonh@gmail.com>
Co-Author: Claudie
"""

import os
import sqlite3
import random
from pathlib import Path
from typing import Optional

from image_io import NAS_PATH_MAP

# --- Concept -> category mapping ---
CONCEPT_CATEGORIES = {
    "casual": ["top", "bottom", "shoes"],
    "street": ["top", "bottom", "outer", "shoes"],
    "formal": ["top", "bottom", "shoes", "accessory"],
    "sporty": ["top", "bottom", "shoes"],
    "date": ["top", "bottom", "shoes", "accessory"],
    "minimal": ["top", "bottom", "shoes"],
    "cozy": ["top", "outer", "bottom", "shoes"],
}

# Platform-specific default catalog.db paths
_CATALOG_DEFAULTS = [
    NAS_PATH_MAP["macos"] + "Claudie/product_catalog/catalog.db",
    NAS_PATH_MAP["windows"] + "Claudie/product_catalog/catalog.db",
    NAS_PATH_MAP["unc"] + "Claudie/product_catalog/catalog.db",
]


def resolve_product_input(product_ids=None, product_id=None, product_query=None):
    """Resolve product input by priority: product_ids > product_id > product_query."""
    if product_ids is not None:
        return ("product_ids", product_ids)
    elif product_id is not None:
        return ("product_id", product_id)
    elif product_query is not None:
        return ("product_query", product_query)
    else:
        raise ValueError(
            "At least one product selection method must be provided: "
            "product_ids, product_id, or product_query"
        )


def get_catalog_db_path(env_var="PRODUCT_CATALOG_DB") -> str:
    """Auto-detect catalog.db path across platforms.

    Checks the environment variable first, then tries platform defaults.

    Raises:
        FileNotFoundError: If no catalog.db found anywhere.
    """
    db_path = os.environ.get(env_var)
    if db_path and Path(db_path).exists():
        return db_path

    for candidate in _CATALOG_DEFAULTS:
        if Path(candidate).exists():
            return candidate

    searched = db_path if db_path else str(_CATALOG_DEFAULTS)
    raise FileNotFoundError(
        f"Product catalog database not found. "
        f"Set {env_var} environment variable. Searched: {searched}"
    )


def suggest_outfit_items(
    db_path: str, concept: str, brand_vibe: Optional[list] = None
) -> list:
    """Suggest 3 coordinated outfit proposals from catalog DB.

    Returns list of up to 3 dicts, each with "option" (A/B/C), "items" list,
    "description", and "rationale".
    """
    categories = CONCEPT_CATEGORIES.get(concept, ["top", "bottom", "shoes"])

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    proposals = []

    for option_idx, option_label in enumerate(["A", "B", "C"]):
        items = []
        for cat in categories:
            # Build query with brand affinity
            query = "SELECT product_id, brand, name, price, colors, materials, local_image_path FROM products WHERE 1=1"
            params = []

            # Category filter (exact match on category field)
            query += " AND category = ?"
            params.append(cat)

            # Brand affinity (prefer profile brands but don't require)
            if brand_vibe:
                brand_clause = " OR ".join(["brand LIKE ?" for _ in brand_vibe])
                query += f" AND ({brand_clause} OR 1=1)"
                params.extend([f"%{b}%" for b in brand_vibe])

            query += " ORDER BY RANDOM() LIMIT 5"

            try:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                if rows:
                    # Pick one (with some randomness per proposal)
                    row = rows[min(option_idx, len(rows) - 1)]
                    items.append({
                        "product_id": row["product_id"],
                        "brand": row["brand"],
                        "name": row["name"],
                        "category": cat,
                        "price": str(row["price"]) if row["price"] else "",
                        "color": row["colors"] if row["colors"] else "",
                    })
            except Exception:
                continue

        if len(items) >= 2:  # minimum: top + bottom
            proposals.append({
                "option": option_label,
                "description": f"{concept.capitalize()} look",
                "items": items,
                "rationale": f"Coordinated {concept} outfit",
            })

    conn.close()
    return proposals


def fetch_products(
    db_path: str,
    product_ids: Optional[list] = None,
    product_id: Optional[str] = None,
    product_query: Optional[str] = None,
) -> list:
    """Fetch product details from catalog DB.

    Returns list of product dicts with keys matching DB columns:
    product_id, brand, name, category, price, colors, materials, local_image_path.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    products = []

    if product_ids is not None:
        input_type, input_value = "product_ids", product_ids
    elif product_id is not None:
        input_type, input_value = "product_id", product_id
    elif product_query is not None:
        input_type, input_value = "product_query", product_query
    else:
        conn.close()
        return products

    if input_type == "product_ids":
        for pid in input_value:
            row = conn.execute(
                "SELECT * FROM products WHERE product_id = ?", (pid,)
            ).fetchone()
            if row:
                products.append(dict(row))
    elif input_type == "product_id":
        row = conn.execute(
            "SELECT * FROM products WHERE product_id = ?", (input_value,)
        ).fetchone()
        if row:
            products.append(dict(row))
    elif input_type == "product_query":
        rows = conn.execute(
            "SELECT * FROM products WHERE name LIKE ? OR brand LIKE ? LIMIT 1",
            (f"%{input_value}%", f"%{input_value}%"),
        ).fetchall()
        for row in rows:
            products.append(dict(row))

    conn.close()
    return products
