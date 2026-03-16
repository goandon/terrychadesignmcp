# design_db.py
"""Design history & concept management database (SQLite).

Tracks image generation history and organizes outputs into named concepts/series.
Uses stdlib sqlite3 — no external dependencies required.

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    character_name TEXT NOT NULL,
    description TEXT,
    tags TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, character_name)
);

CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    profile_name TEXT,
    concept_id INTEGER,
    tool TEXT NOT NULL,
    style TEXT,
    camera_preset TEXT,
    output_mode TEXT,
    prompt TEXT,
    model TEXT,
    image_size TEXT,
    shot_type TEXT,
    image_path TEXT NOT NULL,
    composite_path TEXT,
    product_ids TEXT,
    rating INTEGER DEFAULT 0,
    favorite BOOLEAN DEFAULT FALSE,
    tags TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE INDEX IF NOT EXISTS idx_gen_character ON generations(character_name);
CREATE INDEX IF NOT EXISTS idx_gen_concept   ON generations(concept_id);
CREATE INDEX IF NOT EXISTS idx_gen_created   ON generations(created_at);
CREATE INDEX IF NOT EXISTS idx_gen_favorite  ON generations(favorite);
CREATE INDEX IF NOT EXISTS idx_concept_character ON concepts(character_name);
CREATE INDEX IF NOT EXISTS idx_concept_status    ON concepts(status);
"""

# All columns accepted by record_generation()
_GENERATION_COLUMNS = {
    "character_name", "profile_name", "concept_id", "tool", "style",
    "camera_preset", "output_mode", "prompt", "model", "image_size",
    "shot_type", "image_path", "composite_path", "product_ids",
    "rating", "favorite", "tags", "notes",
}


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(zip([col[0] for col in cursor.description], row))


class DesignDB:
    """SQLite-backed store for design generation history and concept grouping.

    Parameters
    ----------
    db_path:
        Explicit path to the SQLite file.  When *None* the path is derived
        from the ``TERRYCHA_DESIGN_OUTPUT_DIR`` environment variable (or a
        default under the user's home directory).  The resolved path can be
        further overridden by ``TERRYCHA_DESIGN_DB``.
    """

    def __init__(self, db_path: "Path | str | None" = None) -> None:
        if db_path is None:
            output_dir = Path(
                os.environ.get(
                    "TERRYCHA_DESIGN_OUTPUT_DIR",
                    str(Path.home() / "terrycha_design_output"),
                )
            )
            db_path = output_dir / "design_history.db"

        # Allow env-var override of any caller-supplied path as well
        db_path = Path(os.environ.get("TERRYCHA_DESIGN_DB", str(db_path)))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path: Path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    @staticmethod
    def _encode_tags(tags: list[str] | None) -> str | None:
        if tags is None:
            return None
        return json.dumps(tags)

    @staticmethod
    def _decode_tags(raw: str | None) -> list[str] | None:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    def _row_dict(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
        d = _row_to_dict(cursor, row)
        # Decode JSON-encoded tags back to list
        if "tags" in d:
            d["tags"] = self._decode_tags(d["tags"])
        # Convert SQLite integer booleans to Python bool
        if "favorite" in d and d["favorite"] is not None:
            d["favorite"] = bool(d["favorite"])
        return d

    # ------------------------------------------------------------------
    # Concept management
    # ------------------------------------------------------------------

    def create_concept(
        self,
        name: str,
        character_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> int:
        """Insert a new concept row and return its id.

        Raises ``sqlite3.IntegrityError`` (a subclass of ``Exception``) when
        the (name, character_name) pair already exists.
        """
        sql = """
            INSERT INTO concepts (name, character_name, description, tags)
            VALUES (?, ?, ?, ?)
        """
        with self._connect() as conn:
            cur = conn.execute(
                sql,
                (name, character_name, description, self._encode_tags(tags)),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def resolve_concept(self, name: str, character_name: str) -> int:
        """Return the id for (name, character_name), creating it if absent."""
        sql = "SELECT id FROM concepts WHERE name = ? AND character_name = ?"
        with self._connect() as conn:
            row = conn.execute(sql, (name, character_name)).fetchone()
            if row is not None:
                return row[0]
            cur = conn.execute(
                "INSERT INTO concepts (name, character_name) VALUES (?, ?)",
                (name, character_name),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def list_concepts(
        self,
        character: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return a list of concept dicts matching the supplied filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if character is not None:
            conditions.append("character_name = ?")
            params.append(character)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT * FROM concepts
            {where}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()

        results = [self._row_dict(cur, r) for r in rows]

        # Post-filter by tag (tags stored as JSON array)
        if tag is not None:
            results = [r for r in results if tag in (r.get("tags") or [])]

        return results

    def update_concept_status(self, concept_id: int, status: str) -> None:
        """Update the status and updated_at timestamp of a concept."""
        sql = """
            UPDATE concepts
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        with self._connect() as conn:
            conn.execute(sql, (status, concept_id))

    # ------------------------------------------------------------------
    # Generation recording
    # ------------------------------------------------------------------

    def record_generation(self, **kwargs: Any) -> int:
        """Insert a generation row and return its id.

        All keyword arguments must correspond to column names in the
        ``generations`` table.  Unrecognised keys are silently ignored to
        keep the API forward-compatible.
        """
        data = {k: v for k, v in kwargs.items() if k in _GENERATION_COLUMNS}

        # Encode tags list → JSON string
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = self._encode_tags(data["tags"])

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO generations ({columns}) VALUES ({placeholders})"

        with self._connect() as conn:
            cur = conn.execute(sql, list(data.values()))
            return cur.lastrowid  # type: ignore[return-value]

    def search_generations(
        self,
        character: str | None = None,
        concept: str | None = None,
        style: str | None = None,
        rating_min: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        favorite_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return generation rows matching the supplied filters.

        When *concept* is a string name, a JOIN against the concepts table is
        performed to resolve the name.
        """
        joins = ""
        conditions: list[str] = []
        params: list[Any] = []

        if concept is not None:
            joins = "JOIN concepts c ON g.concept_id = c.id"
            conditions.append("c.name = ?")
            params.append(concept)

        if character is not None:
            conditions.append("g.character_name = ?")
            params.append(character)
        if style is not None:
            conditions.append("g.style = ?")
            params.append(style)
        if rating_min is not None:
            conditions.append("g.rating >= ?")
            params.append(rating_min)
        if date_from is not None:
            conditions.append("g.created_at >= ?")
            params.append(date_from)
        if date_to is not None:
            conditions.append("g.created_at <= ?")
            params.append(date_to)
        if favorite_only:
            conditions.append("g.favorite = 1")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT g.* FROM generations g
            {joins}
            {where}
            ORDER BY g.created_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()

        return [self._row_dict(cur, r) for r in rows]

    def rate_generation(
        self,
        gen_id: int,
        rating: int | None = None,
        favorite: bool | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
    ) -> None:
        """Update rating, favorite flag, tags, and/or notes on a generation row."""
        updates: list[str] = []
        params: list[Any] = []

        if rating is not None:
            updates.append("rating = ?")
            params.append(rating)
        if favorite is not None:
            updates.append("favorite = ?")
            params.append(1 if favorite else 0)
        if tags is not None:
            updates.append("tags = ?")
            params.append(self._encode_tags(tags))
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)

        if not updates:
            return

        params.append(gen_id)
        sql = f"UPDATE generations SET {', '.join(updates)} WHERE id = ?"
        with self._connect() as conn:
            conn.execute(sql, params)
