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

CREATE TABLE IF NOT EXISTS emoji_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT 'v1.0',
    theme_tag TEXT,
    style TEXT DEFAULT 'chibi_sd',
    grid_size TEXT DEFAULT '4x4',
    total_count INTEGER NOT NULL,
    sheet_count INTEGER DEFAULT 1,
    base_set TEXT,
    special_count INTEGER DEFAULT 0,
    custom_count INTEGER DEFAULT 0,
    reference_images TEXT,
    model TEXT,
    image_size TEXT,
    output_dir TEXT NOT NULL,
    manifest_path TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS emoji_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id INTEGER NOT NULL,
    grid_index INTEGER NOT NULL,
    sheet_number INTEGER DEFAULT 1,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    label_ko TEXT,
    category TEXT NOT NULL,
    prompt TEXT,
    file_path TEXT NOT NULL,
    platforms TEXT,
    detection_confidence REAL,
    status TEXT DEFAULT 'ok',
    is_favorite BOOLEAN DEFAULT FALSE,
    rating INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (set_id) REFERENCES emoji_sets(id)
);

CREATE INDEX IF NOT EXISTS idx_emoji_set_char  ON emoji_sets(character_name);
CREATE INDEX IF NOT EXISTS idx_emoji_set_theme ON emoji_sets(theme_tag);
CREATE INDEX IF NOT EXISTS idx_emoji_item_set  ON emoji_items(set_id);
CREATE INDEX IF NOT EXISTS idx_emoji_item_key  ON emoji_items(key);
CREATE INDEX IF NOT EXISTS idx_emoji_item_cat  ON emoji_items(category);

CREATE TABLE IF NOT EXISTS emoji_animations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    set_id INTEGER,
    name TEXT NOT NULL,
    emoji_keys TEXT NOT NULL,
    mode TEXT DEFAULT 'sequential',
    frame_delay_ms INTEGER DEFAULT 200,
    loop_count INTEGER DEFAULT 0,
    gif_path TEXT,
    webp_path TEXT,
    gif_discord_path TEXT,
    frame_count INTEGER NOT NULL,
    is_favorite BOOLEAN DEFAULT FALSE,
    rating INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (set_id) REFERENCES emoji_sets(id)
);

CREATE INDEX IF NOT EXISTS idx_emoji_anim_char ON emoji_animations(character_name);
CREATE INDEX IF NOT EXISTS idx_emoji_anim_set ON emoji_animations(set_id);
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
            # Migration: add notes column to emoji_items if missing
            try:
                conn.execute("SELECT notes FROM emoji_items LIMIT 0")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE emoji_items ADD COLUMN notes TEXT")

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

    # ------------------------------------------------------------------
    # Emoji set management
    # ------------------------------------------------------------------

    #: All columns accepted by create_emoji_set()
    _EMOJI_SET_COLUMNS = {
        "character_name", "version", "theme_tag", "style", "grid_size",
        "total_count", "sheet_count", "base_set", "special_count", "custom_count",
        "reference_images", "model", "image_size", "output_dir",
        "manifest_path", "notes",
    }

    def create_emoji_set(self, **kwargs: Any) -> int:
        """Insert a new emoji_set row and return its id.

        Required kwargs: character_name, total_count, output_dir.
        """
        data = {k: v for k, v in kwargs.items() if k in self._EMOJI_SET_COLUMNS}
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO emoji_sets ({columns}) VALUES ({placeholders})"
        with self._connect() as conn:
            cur = conn.execute(sql, list(data.values()))
            return cur.lastrowid  # type: ignore[return-value]

    def get_emoji_set(self, set_id: int) -> dict[str, Any] | None:
        """Return the emoji_set row for *set_id*, or None if not found."""
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM emoji_sets WHERE id = ?", (set_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(cur, row)

    def list_emoji_sets(
        self,
        character_name: str | None = None,
        theme_tag: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return emoji_set rows matching the supplied filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if character_name is not None:
            conditions.append("character_name = ?")
            params.append(character_name)
        if theme_tag is not None:
            conditions.append("theme_tag = ?")
            params.append(theme_tag)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM emoji_sets {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]

    def delete_emoji_set(self, set_id: int) -> bool:
        """Delete all emoji_items for *set_id*, then delete the set row.

        Returns True if the set existed and was deleted, False otherwise.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM emoji_sets WHERE id = ?", (set_id,)
            ).fetchone()
            if existing is None:
                return False
            conn.execute("DELETE FROM emoji_items WHERE set_id = ?", (set_id,))
            conn.execute("DELETE FROM emoji_sets WHERE id = ?", (set_id,))
        return True

    # ------------------------------------------------------------------
    # Emoji item management
    # ------------------------------------------------------------------

    #: All columns accepted by add_emoji_item()
    _EMOJI_ITEM_COLUMNS = {
        "set_id", "grid_index", "sheet_number", "key", "label", "label_ko",
        "category", "prompt", "file_path", "platforms", "detection_confidence",
        "status", "is_favorite", "rating", "notes",
    }

    def add_emoji_item(self, set_id: int, **kwargs: Any) -> int:
        """Insert an emoji_item row and return its id."""
        data: dict[str, Any] = {
            k: v for k, v in kwargs.items() if k in self._EMOJI_ITEM_COLUMNS
        }
        data["set_id"] = set_id
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO emoji_items ({columns}) VALUES ({placeholders})"
        with self._connect() as conn:
            cur = conn.execute(sql, list(data.values()))
            return cur.lastrowid  # type: ignore[return-value]

    def get_emoji_items(self, set_id: int) -> list[dict[str, Any]]:
        """Return all emoji_items for *set_id*, ordered by grid_index."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM emoji_items WHERE set_id = ? ORDER BY grid_index ASC",
                (set_id,),
            )
            rows = cur.fetchall()
        results = []
        for row in rows:
            d = _row_to_dict(cur, row)
            # Convert SQLite integer booleans to Python bool
            if "is_favorite" in d and d["is_favorite"] is not None:
                d["is_favorite"] = bool(d["is_favorite"])
            results.append(d)
        return results

    def find_emoji(self, character_name: str, key: str) -> list[dict[str, Any]]:
        """Return emoji_items matching *key* for *character_name* across all sets."""
        sql = """
            SELECT ei.*
            FROM emoji_items ei
            JOIN emoji_sets es ON ei.set_id = es.id
            WHERE es.character_name = ? AND ei.key = ?
            ORDER BY ei.created_at DESC
        """
        with self._connect() as conn:
            cur = conn.execute(sql, (character_name, key))
            rows = cur.fetchall()
        results = []
        for row in rows:
            d = _row_to_dict(cur, row)
            if "is_favorite" in d and d["is_favorite"] is not None:
                d["is_favorite"] = bool(d["is_favorite"])
            results.append(d)
        return results

    def update_emoji_item(self, item_id: int, **kwargs: Any) -> bool:
        """Update specified fields on an emoji_item row.

        Returns True if the row existed and was updated, False otherwise.
        """
        data = {k: v for k, v in kwargs.items() if k in self._EMOJI_ITEM_COLUMNS}
        data.pop("set_id", None)  # Prevent reassigning the parent set
        if not data:
            return False
        updates = [f"{col} = ?" for col in data]
        params = list(data.values())
        params.append(item_id)
        sql = f"UPDATE emoji_items SET {', '.join(updates)} WHERE id = ?"
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount > 0

    def rate_emoji(
        self,
        item_id: int,
        rating: int | None = None,
        favorite: bool | None = None,
    ) -> bool:
        """Update rating and/or favorite flag on an emoji_item row.

        Returns True if the row existed and was updated, False otherwise.
        """
        updates: list[str] = []
        params: list[Any] = []

        if rating is not None:
            updates.append("rating = ?")
            params.append(rating)
        if favorite is not None:
            updates.append("is_favorite = ?")
            params.append(1 if favorite else 0)

        if not updates:
            return False

        params.append(item_id)
        sql = f"UPDATE emoji_items SET {', '.join(updates)} WHERE id = ?"
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount > 0

    def export_manifest(self, set_id: int, output_dir: str) -> str:
        """Build a manifest dict from the set and its items, write as JSON.

        Returns the absolute path to the written manifest file.

        Raises ``ValueError`` if *set_id* does not exist.
        """
        emoji_set = self.get_emoji_set(set_id)
        if emoji_set is None:
            raise ValueError(f"Emoji set {set_id} not found")

        items = self.get_emoji_items(set_id)

        # Parse reference_images from JSON string to list
        raw_refs = emoji_set.get("reference_images")
        if raw_refs is not None:
            try:
                reference_images = json.loads(raw_refs)
            except (json.JSONDecodeError, TypeError):
                reference_images = []
        else:
            reference_images = []

        # Build expressions list with 1-based index and spec-required fields
        expressions = []
        for item in items:
            # Parse platforms JSON string to dict
            raw_platforms = item.get("platforms")
            if raw_platforms is not None:
                try:
                    platforms_dict = json.loads(raw_platforms)
                except (json.JSONDecodeError, TypeError):
                    platforms_dict = {}
            else:
                platforms_dict = {}

            expressions.append({
                "index": item["grid_index"] + 1,
                "key": item["key"],
                "label": item["label"],
                "label_ko": item.get("label_ko"),
                "category": item["category"],
                "file": item["file_path"],
                "sheet": item.get("sheet_number", 1),
                "platforms": platforms_dict,
            })

        manifest: dict[str, Any] = {
            "version": emoji_set.get("version", "v1.0"),
            "character": emoji_set["character_name"],
            "style": emoji_set.get("style"),
            "theme_tag": emoji_set.get("theme_tag"),
            "created_at": emoji_set.get("created_at"),
            "grid_size": emoji_set.get("grid_size"),
            "sheet_count": emoji_set.get("sheet_count", 1),
            "total_count": emoji_set.get("total_count"),
            "model": emoji_set.get("model"),
            "image_size": emoji_set.get("image_size"),
            "reference_images": reference_images,
            "expressions": expressions,
            "platforms": ["telegram", "discord", "line", "kakaotalk", "slack", "whatsapp", "ico"],
            "db_set_id": set_id,
        }

        out_path = Path(output_dir) / f"emoji_set_{set_id}_manifest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        # Update manifest_path in DB
        with self._connect() as conn:
            conn.execute(
                "UPDATE emoji_sets SET manifest_path = ? WHERE id = ?",
                (str(out_path), set_id),
            )

        return str(out_path)

    # ------------------------------------------------------------------
    # Emoji animation management
    # ------------------------------------------------------------------

    #: All columns accepted by create_animation()
    _EMOJI_ANIMATION_COLUMNS = {
        "character_name", "set_id", "name", "emoji_keys", "mode",
        "frame_delay_ms", "loop_count", "gif_path", "webp_path",
        "gif_discord_path", "frame_count", "is_favorite", "rating",
    }

    def create_animation(self, **kwargs: Any) -> int:
        """Insert a new emoji_animations row and return its id.

        Required kwargs: character_name, name, emoji_keys, frame_count.
        ``emoji_keys`` should be a JSON-encoded string or a Python list
        (auto-encoded to JSON if a list is supplied).
        """
        data = {k: v for k, v in kwargs.items() if k in self._EMOJI_ANIMATION_COLUMNS}

        # Auto-encode emoji_keys list → JSON string
        if "emoji_keys" in data and isinstance(data["emoji_keys"], list):
            data["emoji_keys"] = json.dumps(data["emoji_keys"])

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO emoji_animations ({columns}) VALUES ({placeholders})"
        with self._connect() as conn:
            cur = conn.execute(sql, list(data.values()))
            return cur.lastrowid  # type: ignore[return-value]

    def get_animation(self, anim_id: int) -> dict[str, Any] | None:
        """Return the emoji_animations row for *anim_id*, or None if not found."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM emoji_animations WHERE id = ?", (anim_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        d = _row_to_dict(cur, row)
        # Convert is_favorite integer to Python bool
        if "is_favorite" in d and d["is_favorite"] is not None:
            d["is_favorite"] = bool(d["is_favorite"])
        # Decode emoji_keys JSON string to list
        if "emoji_keys" in d and d["emoji_keys"] is not None:
            try:
                d["emoji_keys"] = json.loads(d["emoji_keys"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def list_animations(
        self,
        character_name: str | None = None,
        set_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return emoji_animations rows matching the supplied filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if character_name is not None:
            conditions.append("character_name = ?")
            params.append(character_name)
        if set_id is not None:
            conditions.append("set_id = ?")
            params.append(set_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = (
            f"SELECT * FROM emoji_animations {where} ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)

        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()

        results = []
        for row in rows:
            d = _row_to_dict(cur, row)
            if "is_favorite" in d and d["is_favorite"] is not None:
                d["is_favorite"] = bool(d["is_favorite"])
            if "emoji_keys" in d and d["emoji_keys"] is not None:
                try:
                    d["emoji_keys"] = json.loads(d["emoji_keys"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def delete_animation(self, anim_id: int) -> bool:
        """Delete the emoji_animations row for *anim_id*.

        Returns True if the row existed and was deleted, False otherwise.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM emoji_animations WHERE id = ?", (anim_id,)
            ).fetchone()
            if existing is None:
                return False
            conn.execute("DELETE FROM emoji_animations WHERE id = ?", (anim_id,))
        return True

    def rate_animation(
        self,
        anim_id: int,
        rating: int | None = None,
        favorite: bool | None = None,
    ) -> bool:
        """Update rating and/or is_favorite flag on an emoji_animations row.

        Returns True if the row existed and was updated, False otherwise.
        """
        updates: list[str] = []
        params: list[Any] = []

        if rating is not None:
            updates.append("rating = ?")
            params.append(rating)
        if favorite is not None:
            updates.append("is_favorite = ?")
            params.append(1 if favorite else 0)

        if not updates:
            return False

        params.append(anim_id)
        sql = f"UPDATE emoji_animations SET {', '.join(updates)} WHERE id = ?"
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount > 0
