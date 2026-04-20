from __future__ import annotations

from typing import Any, Iterable, Iterator


def iter_tsv_lines(records: Iterable[dict[str, Any]]) -> Iterator[str]:
    yield "path\tpermissions"
    for record in records:
        yield (
            f"{_escape_tsv(str(record['path']))}\t{_escape_tsv(str(record['permissions_display']))}"
        )


def _escape_tsv(value: str) -> str:
    return value.replace("\t", " ").replace("\n", " ")
