from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@dataclass(slots=True)
class Item:
    id: str
    name: str
    mime_type: str
    parent_ids: list[str] = field(default_factory=list)
    drive_id: str | None = None
    owners: list[str] = field(default_factory=list)
    permissions: list[dict[str, Any]] = field(default_factory=list)
    size: str | None = None
    modified_time: str | None = None
    web_view_link: str | None = None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME_TYPE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SnapshotError:
    item_id: str
    operation: str
    message: str
    kind: str | None = None
    reason: str | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)
