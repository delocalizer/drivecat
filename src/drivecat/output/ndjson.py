from __future__ import annotations

import json
from typing import Any, Iterable, Iterator


def iter_ndjson_lines(records: Iterable[dict[str, Any]]) -> Iterator[str]:
    for record in records:
        yield json.dumps(record, sort_keys=True)
