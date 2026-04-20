from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from drivecat.gws import GwsClient, GwsError
from drivecat.models import Item, SnapshotError
from drivecat.store import CollectionStore


ProgressHook = Callable[[dict[str, Any]], None]


def collect_to_store(
    root_id: str,
    client: GwsClient,
    *,
    store_path: Path,
    progress_hook: ProgressHook | None = None,
) -> dict[str, Any]:
    root_raw = client.get_file(root_id)
    root_item = _to_item(root_raw)

    with CollectionStore(store_path) as store:
        store.initialize_root(root_item=root_item)
        processed_folders = 0

        while True:
            folder_id = store.pop_next_folder()
            if folder_id is None:
                break

            folder = store.get_item(folder_id)
            if not folder.is_folder:
                store.mark_folder_done(folder_id)
                continue

            staged_items: dict[str, Item] = {}
            try:
                for raw_child in client.iter_children(folder_id):
                    child = _to_item(raw_child)
                    staged_items[child.id] = child
            except GwsError as exc:
                store.record_folder_error(
                    folder_id=folder_id,
                    error=SnapshotError(
                        item_id=folder_id,
                        operation="list_children",
                        message=str(exc),
                        kind=exc.kind,
                        reason=exc.reason,
                        exit_code=exc.exit_code,
                    ).to_dict(),
                )
                processed_folders += 1
                _emit_progress(progress_hook, processed_folders=processed_folders)
                continue

            sorted_children = sorted(staged_items.values(), key=_sort_key)
            store.record_folder_success(folder_id=folder_id, children=sorted_children)
            processed_folders += 1
            _emit_progress(progress_hook, processed_folders=processed_folders)

        counts = store.counts()
        return {
            "root_id": root_item.id,
            "processed_folders": processed_folders,
            "item_count": counts["items"],
            "edge_count": counts["edges"],
            "error_count": counts["errors"],
        }


def _to_item(raw: dict[str, Any]) -> Item:
    owners = []
    for owner in raw.get("owners", []):
        owners.append(owner.get("emailAddress") or owner.get("displayName") or "unknown")

    permissions = []
    for permission in raw.get("permissions", []):
        permissions.append(
            {
                "id": permission.get("id"),
                "type": permission.get("type"),
                "role": permission.get("role"),
                "displayName": permission.get("displayName"),
                "emailAddress": permission.get("emailAddress"),
                "domain": permission.get("domain"),
            }
        )

    return Item(
        id=raw["id"],
        name=raw.get("name", raw["id"]),
        mime_type=raw.get("mimeType", "application/octet-stream"),
        parent_ids=raw.get("parents", []),
        drive_id=raw.get("driveId"),
        owners=owners,
        permissions=permissions,
        size=raw.get("size"),
        modified_time=raw.get("modifiedTime"),
        web_view_link=raw.get("webViewLink"),
    )


def _sort_key(item: Item) -> tuple[int, str]:
    return (0 if item.is_folder else 1, item.name.lower(), item.id)


def _emit_progress(
    progress_hook: ProgressHook | None,
    *,
    processed_folders: int,
) -> None:
    if progress_hook is None:
        return
    progress_hook({"processed_folders": processed_folders})
