from __future__ import annotations

import argparse
import sys
from pathlib import Path

from drivecat.collector import collect_to_store
from drivecat.gws import DEFAULT_PAGE_LIMIT, MIN_GWS_VERSION, GwsClient, GwsError
from drivecat.output.ndjson import iter_ndjson_lines
from drivecat.output.tree import render_tree_output
from drivecat.output.tsv import iter_tsv_lines
from drivecat.store import CollectionStore, is_store_path, load_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drivecat")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect a Drive folder tree into a local SQLite database",
    )
    collect_parser.add_argument(
        "db",
        type=Path,
        help="Path to the output SQLite database file.",
    )
    collect_parser.add_argument(
        "--root-id",
        default="root",
        help="Drive folder ID to start from. Defaults to the authenticated user's root.",
    )
    collect_parser.add_argument(
        "--page-limit",
        type=int,
        default=DEFAULT_PAGE_LIMIT,
        help=f"Maximum paginated gws pages to fetch per folder listing. Default: {DEFAULT_PAGE_LIMIT}.",
    )
    collect_parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Print a progress message every N processed folders. State is persisted to SQLite continuously. Default: 100.",
    )

    output_parser = subparsers.add_parser(
        "output",
        help="Write one of the supported stdout output formats from a collected SQLite database",
    )
    output_parser.add_argument("source", type=Path, help="Path to a collected SQLite database file.")
    output_parser.add_argument(
        "--format",
        choices=("tree", "tsv", "ndjson"),
        required=True,
        help="Output format.",
    )
    output_parser.add_argument(
        "--folders-only",
        action="store_true",
        help="Only display folders in tree output.",
    )
    output_parser.add_argument(
        "-L",
        "--depth",
        type=int,
        help="Maximum display depth for tree output, like `tree -L`. 1 shows only the root.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "collect":
            if args.checkpoint_every < 1:
                parser.exit(status=3, message="drivecat: checkpoint interval must be >= 1\n")
            client = GwsClient(page_limit=args.page_limit)
            def progress_hook(progress: dict[str, object]) -> None:
                processed_folders = int(progress["processed_folders"])
                if processed_folders % args.checkpoint_every != 0:
                    return
                print(
                    f"Persisted progress to {args.db} after {processed_folders} folders",
                    flush=True,
                )

            result = collect_to_store(
                args.root_id,
                client,
                store_path=args.db,
                progress_hook=progress_hook,
            )
            print(f"Wrote collection database to {args.db}")
            version_text = ".".join(str(part) for part in client.version)
            min_version_text = ".".join(str(part) for part in MIN_GWS_VERSION)
            print(f"Used gws {version_text} (minimum supported: {min_version_text})")
            print(
                f"Collected {result['item_count']} items across {result['processed_folders']} folders"
            )
            if result["error_count"]:
                print(f"Completed with {result['error_count']} skipped folder errors")
            return 0

        if args.command == "output":
            if not is_store_path(args.source):
                parser.exit(status=3, message="drivecat: expected a collected SQLite database file\n")
            if args.format == "tree":
                with CollectionStore(args.source) as store:
                    snapshot = load_snapshot(args.source)
                    print(
                        render_tree_output(
                            snapshot,
                            folders_only=args.folders_only,
                            depth=args.depth,
                        )
                    )
                    _write_error_warning(store)
                return 0

            if args.folders_only:
                parser.exit(status=3, message="drivecat: --folders-only is only valid with --format tree\n")
            if args.depth is not None:
                parser.exit(status=3, message="drivecat: --depth is only valid with --format tree\n")

            # unordered record-by-record output formats
            with CollectionStore(args.source) as store:
                records = store.iter_records()
                if args.format == "tsv":
                    for line in iter_tsv_lines(records):
                        sys.stdout.write(line + "\n")
                    _write_error_warning(store)
                    return 0
                if args.format == "ndjson":
                    for line in iter_ndjson_lines(records):
                        sys.stdout.write(line + "\n")
                    _write_error_warning(store)
                    return 0
            return 0
    except GwsError as exc:
        parser.exit(status=2, message=f"drivecat: {exc}\n")
    except ValueError as exc:
        parser.exit(status=3, message=f"drivecat: {exc}\n")

    parser.exit(status=3, message="drivecat: unknown command\n")


def _write_error_warning(store: CollectionStore) -> None:
    errors = list(store.iter_errors())
    if not errors:
        return
    print(
        f"Warnings: {len(errors)} collection errors recorded in snapshot.",
        file=sys.stderr,
    )
