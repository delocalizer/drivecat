import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from drivecat.cli import main
from drivecat.collector import collect_to_store
from drivecat.gws import GwsError
from drivecat.output.ndjson import iter_ndjson_lines
from drivecat.output.tsv import iter_tsv_lines
from drivecat.store import CollectionStore, load_snapshot


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_file(self, file_id: str) -> dict[str, object]:
        self.calls.append(f"get:{file_id}")
        return {
            "id": "root-id",
            "name": "Root",
            "mimeType": "application/vnd.google-apps.folder",
            "permissions": [],
        }

    def iter_children(self, folder_id: str):
        self.calls.append(f"list:{folder_id}")
        if folder_id == "root-id":
            yield {
                "id": "partial-file",
                "name": "Partial File",
                "mimeType": "text/plain",
                "permissions": [],
            }
            raise GwsError("backend error", kind="api_error", api_code=503)
        return
        yield


class CollectorTests(unittest.TestCase):
    def test_partial_folder_failure_does_not_commit_partial_children(self) -> None:
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "out.sqlite3"
            progress_events: list[dict[str, object]] = []
            result = collect_to_store("root", client, store_path=db_path, progress_hook=progress_events.append)
            snapshot = load_snapshot(db_path)

            self.assertEqual(result["error_count"], 1)
            self.assertTrue(snapshot["complete"])
            self.assertNotIn("partial-file", snapshot["items"])
            self.assertEqual(snapshot["children"], {})
            self.assertEqual(len(snapshot["errors"]), 1)
            self.assertEqual(progress_events, [{"processed_folders": 1}])

    def test_collect_to_store_writes_sqlite_primary_artifact(self) -> None:
        class SuccessClient(FakeClient):
            def iter_children(self, folder_id: str):
                self.calls.append(f"list:{folder_id}")
                if folder_id == "root-id":
                    yield {
                        "id": "file-a",
                        "name": "File A",
                        "mimeType": "text/plain",
                        "permissions": [],
                    }

        client = SuccessClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "out.sqlite3"
            result = collect_to_store("root", client, store_path=db_path)
            snapshot = load_snapshot(db_path)

            self.assertTrue(db_path.exists())
            self.assertEqual(result["item_count"], 2)
            self.assertEqual(snapshot["root_id"], "root-id")
            self.assertIn("file-a", snapshot["items"])
            self.assertTrue(snapshot["complete"])

    def test_load_snapshot_rejects_non_sqlite_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "not-a-db.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Expected a collected SQLite database file"):
                load_snapshot(path)

    def test_output_records_are_self_contained(self) -> None:
        class SuccessClient(FakeClient):
            def iter_children(self, folder_id: str):
                self.calls.append(f"list:{folder_id}")
                if folder_id == "root-id":
                    yield {
                        "id": "folder-a",
                        "name": "Folder A",
                        "mimeType": "application/vnd.google-apps.folder",
                        "permissions": [],
                    }
                    yield {
                        "id": "file-a",
                        "name": "File A",
                        "mimeType": "text/plain",
                        "permissions": [
                            {
                                "type": "user",
                                "displayName": "Bob",
                                "emailAddress": "bob@example.com",
                                "role": "owner",
                            }
                        ],
                    }
                elif folder_id == "folder-a":
                    yield {
                        "id": "file-b",
                        "name": "File B",
                        "mimeType": "text/plain",
                        "permissions": [],
                    }

        client = SuccessClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "out.sqlite3"
            collect_to_store("root", client, store_path=db_path)
            with CollectionStore(db_path) as store:
                records = list(store.iter_records())
            self.assertEqual(
                [record["path"] for record in records],
                ["Root:/", "Root:/Folder A", "Root:/Folder A/File B", "Root:/File A"],
            )
            self.assertEqual(records[0]["id"], "root-id")
            self.assertEqual(records[2]["name"], "File B")
            self.assertEqual(records[3]["permissions"][0]["displayName"], "Bob")
            self.assertEqual(records[3]["depth"], 1)
            self.assertEqual(records[3]["path_segments"], ["Root", "File A"])
            self.assertEqual(records[3]["permissions_display"], "[owner:user:Bob <bob@example.com>]")

    def test_iter_errors_returns_recorded_errors(self) -> None:
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "out.sqlite3"
            collect_to_store("root", client, store_path=db_path)
            with CollectionStore(db_path) as store:
                errors = list(store.iter_errors())

            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["item_id"], "root-id")
            self.assertEqual(errors[0]["kind"], "api_error")
            self.assertIsNone(errors[0]["reason"])
            self.assertIsNone(errors[0]["exit_code"])

    def test_output_commands_write_error_warning_to_stderr_for_all_formats(self) -> None:
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "out.sqlite3"
            collect_to_store("root", client, store_path=db_path)

            for output_format in ("tree", "tsv", "ndjson"):
                stdout = StringIO()
                stderr = StringIO()
                with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                    exit_code = main(["output", str(db_path), "--format", output_format])

                self.assertEqual(exit_code, 0)
                self.assertIn("Warnings: 1 collection errors recorded in snapshot.", stderr.getvalue())

    def test_tsv_and_ndjson_output_lines_use_path_and_permissions_fields(self) -> None:
        records = [
            {
                "id": "root-id",
                "name": "MyDrive",
                "mime_type": "application/vnd.google-apps.folder",
                "permissions": [],
                "path": "MyDrive:/",
                "path_segments": ["MyDrive"],
                "depth": 0,
                "permissions_display": "[]",
            },
            {
                "id": "file-a",
                "name": "myfile.txt",
                "mime_type": "text/plain",
                "permissions": [
                    {
                        "type": "group",
                        "displayName": "Editors",
                        "emailAddress": "editors@example.com",
                        "role": "writer",
                    }
                ],
                "path": "MyDrive:/myfile.txt",
                "path_segments": ["MyDrive", "myfile.txt"],
                "depth": 1,
                "permissions_display": "[writer:group:Editors <editors@example.com>]",
            },
        ]
        tsv_lines = list(iter_tsv_lines(records))
        ndjson_lines = list(iter_ndjson_lines(records))

        self.assertEqual(tsv_lines[0], "path\tpermissions")
        self.assertEqual(
            tsv_lines[1:],
            [
                "MyDrive:/\t[]",
                "MyDrive:/myfile.txt\t[writer:group:Editors <editors@example.com>]",
            ],
        )
        self.assertIn('"path": "MyDrive:/myfile.txt"', ndjson_lines[1])
        self.assertIn(
            '"permissions_display": "[writer:group:Editors <editors@example.com>]"',
            ndjson_lines[1],
        )


if __name__ == "__main__":
    unittest.main()
