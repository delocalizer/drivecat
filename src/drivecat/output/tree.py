from __future__ import annotations

from typing import Any

from drivecat.models import FOLDER_MIME_TYPE


def render_tree(
    snapshot: dict[str, Any],
    *,
    folders_only: bool = False,
    max_depth: int | None = None,
) -> str:
    items: dict[str, dict[str, Any]] = snapshot["items"]
    children: dict[str, list[str]] = snapshot.get("children", {})
    root_id = snapshot["root_id"]

    if root_id not in items:
        raise ValueError(f"Root item '{root_id}' is missing from snapshot")

    if max_depth is not None and max_depth < 1:
        raise ValueError("Depth must be >= 1")

    lines: list[str] = [_label(items[root_id])]
    if max_depth == 1:
        return "\n".join(lines)

    child_ids = _filter_children(children.get(root_id, []), items, folders_only)
    for index, child_id in enumerate(child_ids):
        is_last = index == len(child_ids) - 1
        _render_subtree(
            lines,
            items,
            children,
            child_id,
            prefix="",
            is_last=is_last,
            folders_only=folders_only,
            depth=2,
            max_depth=max_depth,
        )
    return "\n".join(lines)


def render_tree_output(snapshot: dict[str, Any], *, folders_only: bool, depth: int | None) -> str:
    return render_tree(snapshot, folders_only=folders_only, max_depth=depth)


def _render_subtree(
    lines: list[str],
    items: dict[str, dict[str, Any]],
    children: dict[str, list[str]],
    item_id: str,
    *,
    prefix: str,
    is_last: bool,
    folders_only: bool,
    depth: int,
    max_depth: int | None,
) -> None:
    connector = "└── " if is_last else "├── "
    lines.append(f"{prefix}{connector}{_label(items[item_id])}")
    if max_depth is not None and depth >= max_depth:
        return

    next_prefix = f"{prefix}{'    ' if is_last else '│   '}"
    child_ids = _filter_children(children.get(item_id, []), items, folders_only)
    for index, child_id in enumerate(child_ids):
        _render_subtree(
            lines,
            items,
            children,
            child_id,
            prefix=next_prefix,
            is_last=index == len(child_ids) - 1,
            folders_only=folders_only,
            depth=depth + 1,
            max_depth=max_depth,
        )


def _filter_children(
    child_ids: list[str],
    items: dict[str, dict[str, Any]],
    folders_only: bool,
) -> list[str]:
    if not folders_only:
        return child_ids
    return [child_id for child_id in child_ids if items[child_id]["mime_type"] == FOLDER_MIME_TYPE]


def _label(item: dict[str, Any]) -> str:
    suffix = "/" if item["mime_type"] == FOLDER_MIME_TYPE else ""
    return f"{item['name']}{suffix} {format_permission_annotation(item)}"


def format_permission_annotation(item: dict[str, Any]) -> str:
    return f"[{format_permission_value(item)}]"


def format_permission_value(item: dict[str, Any]) -> str:
    permissions = item.get("permissions", [])
    if not permissions:
        return ""

    triples: list[str] = []
    for permission in sorted(permissions, key=_permission_sort_key):
        role = permission.get("role") or "unknown"
        grantee_type = permission.get("type") or "unknown"
        grantee_name = _permission_grantee_name(permission)
        triples.append(f"{role}:{grantee_type}:{grantee_name}")
    return "|".join(triples)


def _permission_sort_key(permission: dict[str, Any]) -> tuple[int, int, str, str]:
    role = permission.get("role") or "unknown"
    grantee_type = permission.get("type") or "unknown"
    grantee_name = _permission_grantee_name(permission)
    return (
        _role_sort_order(role),
        _grantee_type_sort_order(grantee_type),
        grantee_name.lower(),
        role,
    )


def _role_sort_order(role: str) -> int:
    return {
        "owner": 0,
        "writer": 1,
        "reader": 2,
    }.get(role, 99)


def _grantee_type_sort_order(grantee_type: str) -> int:
    return {
        "group": 0,
        "user": 1,
    }.get(grantee_type, 99)


def _permission_grantee_name(permission: dict[str, Any]) -> str:
    display_name = permission.get("displayName")
    email_address = permission.get("emailAddress")
    domain = permission.get("domain")
    permission_id = permission.get("id")

    if display_name and email_address:
        return f"{display_name} <{email_address}>"
    if display_name and domain:
        return f"{display_name} <{domain}>"
    if display_name:
        return str(display_name)
    if email_address:
        return str(email_address)
    if domain:
        return str(domain)
    if permission_id:
        return str(permission_id)
    permission_type = permission.get("type")
    if permission_type == "anyone":
        return "anyone"
    return "unknown"
