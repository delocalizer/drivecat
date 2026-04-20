from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from drivecat.models import Item
from drivecat.output.tree import format_permission_annotation


class CollectionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> CollectionStore:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def initialize_root(self, *, root_item: Item) -> None:
        with self.conn:
            self._clear_data()
            self._set_meta("root_id", root_item.id)
            self.upsert_item(root_item)
            self.enqueue_folder(root_item.id)

    def upsert_item(self, item: Item) -> None:
        payload = json.dumps(item.to_dict(), sort_keys=True)
        self.conn.execute(
            """
            INSERT INTO items (item_id, item_json, mime_type, name_lower)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                item_json = excluded.item_json,
                mime_type = excluded.mime_type,
                name_lower = excluded.name_lower
            """,
            (item.id, payload, item.mime_type, item.name.lower()),
        )

    def get_item(self, item_id: str) -> Item:
        row = self.conn.execute(
            "SELECT item_json FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            raise KeyError(item_id)
        return Item(**json.loads(row["item_json"]))

    def enqueue_folder(self, folder_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO folder_queue (folder_id, state)
            VALUES (?, 'pending')
            ON CONFLICT(folder_id) DO NOTHING
            """,
            (folder_id,),
        )

    def pop_next_folder(self) -> str | None:
        row = self.conn.execute(
            """
            SELECT queue_id, folder_id
            FROM folder_queue
            WHERE state = 'pending'
            ORDER BY queue_id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        with self.conn:
            self.conn.execute(
                "UPDATE folder_queue SET state = 'processing' WHERE queue_id = ?",
                (row["queue_id"],),
            )
        return str(row["folder_id"])

    def mark_folder_done(self, folder_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE folder_queue SET state = 'done' WHERE folder_id = ?",
                (folder_id,),
            )

    def record_folder_success(
        self,
        *,
        folder_id: str,
        children: list[Item],
    ) -> None:
        with self.conn:
            for child in children:
                self.upsert_item(child)
            self.conn.execute("DELETE FROM children WHERE parent_id = ?", (folder_id,))
            for index, child in enumerate(children):
                self.conn.execute(
                    """
                    INSERT INTO children (parent_id, child_id, sort_index)
                    VALUES (?, ?, ?)
                    """,
                    (folder_id, child.id, index),
                )
                if child.is_folder:
                    self.enqueue_folder(child.id)
            self.conn.execute(
                "UPDATE folder_queue SET state = 'done' WHERE folder_id = ?",
                (folder_id,),
            )

    def record_folder_error(self, *, folder_id: str, error: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO errors (
                    item_id,
                    operation,
                    message,
                    kind,
                    reason,
                    exit_code
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    folder_id,
                    error.get("operation"),
                    error.get("message"),
                    error.get("kind"),
                    error.get("reason"),
                    error.get("exit_code"),
                ),
            )
            self.conn.execute(
                "UPDATE folder_queue SET state = 'done' WHERE folder_id = ?",
                (folder_id,),
            )

    def materialize_snapshot(self, *, complete: bool) -> dict[str, Any]:
        items = {
            str(row["item_id"]): json.loads(row["item_json"])
            for row in self.conn.execute("SELECT item_id, item_json FROM items ORDER BY item_id")
        }
        children: dict[str, list[str]] = {}
        for row in self.conn.execute(
            "SELECT parent_id, child_id FROM children ORDER BY parent_id, sort_index"
        ):
            parent_id = str(row["parent_id"])
            children.setdefault(parent_id, []).append(str(row["child_id"]))
        errors = list(self.iter_errors())
        snapshot = {
            "snapshot_version": 1,
            "root_id": self._get_meta("root_id"),
            "items": items,
            "children": children,
            "errors": errors,
            "complete": complete,
        }
        return snapshot

    def counts(self) -> dict[str, int]:
        return {
            "items": int(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]),
            "edges": int(self.conn.execute("SELECT COUNT(*) FROM children").fetchone()[0]),
            "errors": int(self.conn.execute("SELECT COUNT(*) FROM errors").fetchone()[0]),
            "folders_done": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM folder_queue WHERE state = 'done'"
                ).fetchone()[0]
            ),
        }

    def iter_errors(self) -> Iterator[dict[str, Any]]:
        for row in self.conn.execute(
            """
            SELECT item_id, operation, message, kind, reason, exit_code
            FROM errors
            ORDER BY error_id
            """
        ):
            yield {
                "item_id": row["item_id"],
                "operation": row["operation"],
                "message": row["message"],
                "kind": row["kind"],
                "reason": row["reason"],
                "exit_code": row["exit_code"],
            }

    def iter_records(self) -> Iterator[dict[str, Any]]:
        root_id = self._get_meta("root_id")
        if root_id is None:
            return

        root_item = self.get_item(root_id)
        stack: list[tuple[str, str, int]] = [(root_id, _rooted_path([root_item.name]), 0)]

        while stack:
            item_id, path_value, depth = stack.pop()
            item = self.get_item(item_id)
            record = item.to_dict()
            record["path"] = path_value
            record["path_segments"] = _path_segments(path_value)
            record["depth"] = depth
            record["permissions_display"] = format_permission_annotation(record)
            yield record

            child_rows = list(
                self.conn.execute(
                    """
                    SELECT child_id
                    FROM children
                    WHERE parent_id = ?
                    ORDER BY sort_index
                    """,
                    (item_id,),
                )
            )
            for row in reversed(child_rows):
                child_id = str(row["child_id"])
                child_item = self.get_item(child_id)
                stack.append((child_id, _append_path(path_value, child_item.name), depth + 1))

    def _get_meta(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY,
                    item_json TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    name_lower TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS children (
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    sort_index INTEGER NOT NULL,
                    PRIMARY KEY (parent_id, child_id)
                );
                CREATE TABLE IF NOT EXISTS errors (
                    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    operation TEXT,
                    message TEXT NOT NULL,
                    kind TEXT,
                    reason TEXT,
                    exit_code INTEGER
                );
                CREATE TABLE IF NOT EXISTS folder_queue (
                    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL CHECK(state IN ('pending', 'processing', 'done'))
                );
                """
            )

    def _clear_data(self) -> None:
        self.conn.executescript(
            """
            DELETE FROM metadata;
            DELETE FROM items;
            DELETE FROM children;
            DELETE FROM errors;
            DELETE FROM folder_queue;
            """
        )


def _rooted_path(segments: list[str]) -> str:
    if not segments:
        return ":/"
    return f"{segments[0]}:/{'/'.join(segments[1:])}" if len(segments) > 1 else f"{segments[0]}:/"


def _append_path(path_value: str, name: str) -> str:
    if path_value.endswith(":/"):
        return f"{path_value}{name}"
    return f"{path_value}/{name}"


def _path_segments(path_value: str) -> list[str]:
    drive_name, _, remainder = path_value.partition(":/")
    if not remainder:
        return [drive_name]
    return [drive_name, *remainder.split("/")]


def load_snapshot(path: Path, *, complete: bool = True) -> dict[str, Any]:
    if not is_store_path(path):
        raise ValueError("Expected a collected SQLite database file")
    with CollectionStore(path) as store:
        return store.materialize_snapshot(complete=complete)


def is_store_path(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'metadata'"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()
