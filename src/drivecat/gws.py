from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from shutil import which
from typing import Any, Iterator


DEFAULT_FIELDS = ",".join(
    [
        "nextPageToken",
        "files(id,name,mimeType,parents,driveId,owners(emailAddress,displayName),permissions(id,type,role,displayName,emailAddress,domain),size,modifiedTime,webViewLink)",
    ]
)

FILE_FIELDS = ",".join(
    [
        "id",
        "name",
        "mimeType",
        "parents",
        "driveId",
        "owners(emailAddress,displayName)",
        "permissions(id,type,role,displayName,emailAddress,domain)",
        "size",
        "modifiedTime",
        "webViewLink",
    ]
)

MIN_GWS_VERSION = (0, 22, 0)
DEFAULT_PAGE_LIMIT = 10000
EXIT_CODE_KIND = {
    1: "api_error",
    2: "auth_error",
    3: "validation_error",
    4: "discovery_error",
    5: "internal_error",
}


class GwsError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: str = "gws_error",
        exit_code: int | None = None,
        reason: str | None = None,
        api_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.exit_code = exit_code
        self.reason = reason
        self.api_code = api_code

    def __str__(self) -> str:
        details: list[str] = [self.message]
        if self.reason:
            details.append(f"reason={self.reason}")
        if self.api_code is not None:
            details.append(f"api_code={self.api_code}")
        if self.exit_code is not None:
            details.append(f"exit_code={self.exit_code}")
        return " ".join(details)


class GwsVersionError(GwsError):
    pass


class GwsPaginationError(GwsError):
    pass


@dataclass(slots=True)
class GwsClient:
    binary: str = "gws"
    min_version: tuple[int, int, int] = MIN_GWS_VERSION
    page_limit: int = DEFAULT_PAGE_LIMIT
    max_retries: int = 3
    retry_base_delay: float = 1.0
    version: tuple[int, int, int] = field(init=False)

    def __post_init__(self) -> None:
        if which(self.binary) is None:
            raise GwsError(
                f"Required binary '{self.binary}' was not found on PATH. Install googleworkspace/cli first."
            )
        if self.page_limit < 1:
            raise GwsError("page_limit must be >= 1", kind="validation_error")
        self.version = self._get_version()
        if self.version < self.min_version:
            found = ".".join(str(part) for part in self.version)
            required = ".".join(str(part) for part in self.min_version)
            raise GwsVersionError(
                f"Unsupported gws version {found}. Require >= {required}.",
                kind="version_error",
            )

    def get_file(self, file_id: str) -> dict[str, Any]:
        cmd = [
            self.binary,
            "drive",
            "files",
            "get",
            "--params",
            json.dumps(
                {
                    "fileId": file_id,
                    "fields": FILE_FIELDS,
                    "supportsAllDrives": True,
                }
            ),
        ]
        return self._run_json_with_retries(
            cmd,
            operation=f"get_file({file_id})",
        )

    def iter_children(self, folder_id: str) -> Iterator[dict[str, Any]]:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": DEFAULT_FIELDS,
            "pageSize": 1000,
            "includeItemsFromAllDrives": True,
            "supportsAllDrives": True,
        }
        cmd = [
            self.binary,
            "drive",
            "files",
            "list",
            "--params",
            json.dumps(params),
            "--page-all",
            "--page-limit",
            str(self.page_limit),
        ]

        attempt = 0
        while True:
            yielded_any = False
            try:
                page_count = 0
                last_next_page_token: str | None = None
                for page in self._run_ndjson_stream(cmd):
                    page_count += 1
                    last_next_page_token = page.get("nextPageToken")
                    for child in page.get("files", []):
                        yielded_any = True
                        yield child

                if page_count >= self.page_limit and last_next_page_token:
                    raise GwsPaginationError(
                        f"Pagination limit reached while listing folder '{folder_id}'. Increase --page-limit.",
                        kind="pagination_limit",
                        reason="nextPageToken_present_after_page_limit",
                    )
                return
            except GwsError as exc:
                if yielded_any or not self._should_retry(exc, attempt):
                    raise
                self._sleep_before_retry(attempt, exc, f"iter_children({folder_id})")
                attempt += 1

    def _run(self, cmd: list[str]) -> dict[str, Any]:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise self._to_error(result)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GwsError(f"Unable to decode gws JSON output: {exc}") from exc

    def _run_json_with_retries(self, cmd: list[str], *, operation: str) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                return self._run(cmd)
            except GwsError as exc:
                if not self._should_retry(exc, attempt):
                    raise
                self._sleep_before_retry(attempt, exc, operation)
                attempt += 1

    def _run_ndjson_stream(self, cmd: list[str]) -> Iterator[dict[str, Any]]:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        raw_stdout_lines: list[str] = []
        parse_error: json.JSONDecodeError | None = None
        try:
            for line in process.stdout:
                raw_line = line
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raw_stdout_lines.append(raw_line)
                    if parse_error is None:
                        parse_error = exc
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read()
            return_code = process.wait()
        finally:
            if process.stdout is not None and hasattr(process.stdout, "close"):
                process.stdout.close()
            if process.stderr is not None and hasattr(process.stderr, "close"):
                process.stderr.close()

        if return_code != 0:
            raise self._to_error(
                subprocess.CompletedProcess(
                    args=cmd,
                    returncode=return_code,
                    stdout="".join(raw_stdout_lines),
                    stderr=stderr,
                )
            )
        if parse_error is not None:
            raise GwsError(f"Unable to decode gws NDJSON output: {parse_error}") from parse_error

    def _get_version(self) -> tuple[int, int, int]:
        result = subprocess.run(
            [self.binary, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise self._to_error(result)

        match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout)
        if match is None:
            raise GwsVersionError(
                f"Unable to parse gws version from output: {result.stdout.strip() or '<empty>'}",
                kind="version_error",
            )
        return tuple(int(part) for part in match.groups())

    def _to_error(self, result: subprocess.CompletedProcess[str]) -> GwsError:
        payload = self._extract_error_payload(result.stdout, result.stderr)
        exit_code = result.returncode
        kind = EXIT_CODE_KIND.get(exit_code, "gws_error")
        if payload is not None:
            error_obj = payload.get("error", {})
            return GwsError(
                error_obj.get("message") or result.stderr.strip() or "gws command failed",
                kind=kind,
                exit_code=exit_code,
                reason=error_obj.get("reason"),
                api_code=error_obj.get("code"),
            )
        return GwsError(
            result.stderr.strip() or result.stdout.strip() or "gws command failed",
            kind=kind,
            exit_code=exit_code,
        )

    def _extract_error_payload(self, stdout: str, stderr: str) -> dict[str, Any] | None:
        for candidate in (stdout, stderr):
            payload = _extract_json_object(candidate)
            if isinstance(payload, dict) and "error" in payload:
                return payload
        return None

    def _should_retry(self, error: GwsError, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        if error.kind == "pagination_limit":
            return False
        if error.api_code in {429, 500, 502, 503, 504}:
            return True
        if error.reason in {
            "rateLimitExceeded",
            "userRateLimitExceeded",
            "backendError",
            "internalError",
        }:
            return True
        if error.kind == "internal_error":
            return True
        lowered = error.message.lower()
        transient_markers = (
            "connection failure",
            "temporarily unavailable",
            "timeout",
            "timed out",
            "connection reset",
            "broken pipe",
        )
        return any(marker in lowered for marker in transient_markers)

    def _sleep_before_retry(self, attempt: int, error: GwsError, operation: str) -> None:
        delay = self.retry_base_delay * (2**attempt)
        time.sleep(delay)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None

    candidates: list[str] = [stripped]
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(stripped[first_brace : last_brace + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None
