import unittest

from drivecat.output.tree import render_tree


class RenderTreeTests(unittest.TestCase):
    def test_render_tree_full_snapshot(self) -> None:
        snapshot = {
            "root_id": "root",
            "items": {
                "root": {
                    "id": "root",
                    "name": "Root",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [
                        {
                            "type": "user",
                            "displayName": "Alice",
                            "emailAddress": "alice@example.com",
                            "role": "reader",
                        },
                        {
                            "type": "group",
                            "displayName": "Editors",
                            "emailAddress": "editors@example.com",
                            "role": "writer",
                        },
                        {
                            "type": "user",
                            "displayName": "Bob",
                            "emailAddress": "bob@example.com",
                            "role": "owner",
                        }
                        ,
                        {
                            "type": "group",
                            "displayName": "Readers",
                            "emailAddress": "readers@example.com",
                            "role": "reader",
                        },
                        {
                            "type": "user",
                            "displayName": "Carol",
                            "emailAddress": "carol@example.com",
                            "role": "writer",
                        },
                    ],
                },
                "folder-a": {
                    "id": "folder-a",
                    "name": "Folder A",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [
                        {
                            "type": "group",
                            "displayName": "My Group",
                            "emailAddress": "group@example.com",
                            "role": "writer",
                        }
                    ],
                },
                "file-a": {
                    "id": "file-a",
                    "name": "File A",
                    "mime_type": "text/plain",
                    "permissions": [{"type": "domain", "domain": "example.com", "role": "reader"}],
                },
            },
            "children": {
                "root": ["folder-a", "file-a"],
                "folder-a": [],
            },
            "errors": [],
        }

        self.assertEqual(
            render_tree(snapshot),
            "Root/ [owner:user:Bob <bob@example.com>|writer:group:Editors <editors@example.com>|writer:user:Carol <carol@example.com>|reader:group:Readers <readers@example.com>|reader:user:Alice <alice@example.com>]\n├── Folder A/ [writer:group:My Group <group@example.com>]\n└── File A [reader:domain:example.com]",
        )

    def test_render_tree_folders_only(self) -> None:
        snapshot = {
            "root_id": "root",
            "items": {
                "root": {
                    "id": "root",
                    "name": "Root",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [],
                },
                "folder-a": {
                    "id": "folder-a",
                    "name": "Folder A",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [
                        {
                            "type": "group",
                            "displayName": "My Group",
                            "emailAddress": "group@example.com",
                            "role": "writer",
                        }
                    ],
                },
                "file-a": {
                    "id": "file-a",
                    "name": "File A",
                    "mime_type": "text/plain",
                    "permissions": [{"type": "domain", "domain": "example.com", "role": "reader"}],
                },
            },
            "children": {
                "root": ["folder-a", "file-a"],
                "folder-a": [],
            },
            "errors": [],
        }

        self.assertEqual(
            render_tree(snapshot, folders_only=True),
            "Root/ []\n└── Folder A/ [writer:group:My Group <group@example.com>]",
        )

    def test_render_tree_rejects_missing_root(self) -> None:
        snapshot = {
            "root_id": "missing-root",
            "items": {
                "actual-root-id": {
                    "id": "actual-root-id",
                    "name": "Root",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [],
                },
            },
            "children": {},
            "errors": [],
        }

        with self.assertRaisesRegex(ValueError, "Root item 'missing-root' is missing from snapshot"):
            render_tree(snapshot)

    def test_render_tree_respects_max_depth(self) -> None:
        snapshot = {
            "root_id": "root",
            "items": {
                "root": {
                    "id": "root",
                    "name": "Root",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [],
                },
                "folder-a": {
                    "id": "folder-a",
                    "name": "Folder A",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [],
                },
                "file-a": {
                    "id": "file-a",
                    "name": "File A",
                    "mime_type": "text/plain",
                    "permissions": [],
                },
                "file-b": {
                    "id": "file-b",
                    "name": "File B",
                    "mime_type": "text/plain",
                    "permissions": [],
                },
            },
            "children": {
                "root": ["folder-a", "file-a"],
                "folder-a": ["file-b"],
            },
            "errors": [],
        }

        self.assertEqual(
            render_tree(snapshot, max_depth=1),
            "Root/ []",
        )
        self.assertEqual(
            render_tree(snapshot, max_depth=2),
            "Root/ []\n├── Folder A/ []\n└── File A []",
        )

    def test_render_tree_rejects_invalid_depth(self) -> None:
        snapshot = {
            "root_id": "root",
            "items": {
                "root": {
                    "id": "root",
                    "name": "Root",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [],
                },
            },
            "children": {"root": []},
            "errors": [],
        }

        with self.assertRaisesRegex(ValueError, "Depth must be >= 1"):
            render_tree(snapshot, max_depth=0)

    def test_render_tree_sorts_permissions_by_role_and_grantee_type(self) -> None:
        snapshot = {
            "root_id": "root",
            "items": {
                "root": {
                    "id": "root",
                    "name": "Root",
                    "mime_type": "application/vnd.google-apps.folder",
                    "permissions": [
                        {"type": "user", "displayName": "Bob", "emailAddress": "bob@example.com", "role": "reader"},
                        {"type": "user", "displayName": "Owner", "emailAddress": "owner@example.com", "role": "owner"},
                        {"type": "group", "displayName": "Readers", "emailAddress": "readers@example.com", "role": "reader"},
                        {"type": "user", "displayName": "Writer User", "emailAddress": "writer-user@example.com", "role": "writer"},
                        {"type": "group", "displayName": "Writers", "emailAddress": "writers@example.com", "role": "writer"},
                    ],
                },
            },
            "children": {"root": []},
            "errors": [],
        }

        self.assertEqual(
            render_tree(snapshot),
            "Root/ [owner:user:Owner <owner@example.com>|writer:group:Writers <writers@example.com>|writer:user:Writer User <writer-user@example.com>|reader:group:Readers <readers@example.com>|reader:user:Bob <bob@example.com>]",
        )


if __name__ == "__main__":
    unittest.main()
