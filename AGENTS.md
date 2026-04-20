# AGENTS.md — drivecat

`drivecat` collects metadata about Google Drive content and emits human-readable or machine-readable views of that collected data.

## Goals

- Collect the structure and selected metadata of a Google Drive, shared drive, or subfolder thereof.
- Persist collected data locally in a form that supports large crawls, partial progress, and repeated read-side output without re-querying Drive.
- Support multiple output views over the same collected dataset, including formats optimized for humans and formats optimized for downstream tools.
- Surface access and permission information clearly enough to support audit, catalog, and structure-discovery use cases.
- Remain robust in the presence of partial failures such as permission errors, transient API failures, and incomplete visibility into some subtrees.

## Principles

- Separate collection from output.
  Collection should build a reusable local artifact. Output commands should read from that artifact rather than re-crawling Drive.
- Prefer durable, incremental state for large crawls.
  The collection path should tolerate interruption and avoid depending on large in-memory aggregates where possible.
- Prefer streaming read-side output where practical.
  Output formats should scale to large datasets and avoid unnecessary whole-dataset materialization.
- Preserve user-meaningful paths and permissions.
  Outputs should make hierarchy and access relationships easy to understand.
- Treat partial visibility as normal.
  Missing access to some objects should degrade results gracefully instead of failing the entire run whenever possible.
- Keep interfaces stable and unsurprising.
  Favor explicit CLI contracts, consistent output semantics, and predictable stored-data behavior.

## Current Architecture

- A collection command talks to Google Drive through `googleworkspace/cli` (`gws`).
- Collection persists local state in a SQLite database.
- Output commands read from the local database and write to stdout in one of the supported formats.
- The database is the primary artifact; output formats are views over that artifact.

## Target Users

- CIOs and document managers who need to understand structure and access across Drive content.
- Drive users who want to understand what is stored where and who has access to it.
- Engineers and analysts who want a local, scriptable representation of Drive metadata.

## Agent Instructions

When acting as an agent in this repo:

1. Start by reading `README.md` and this `AGENTS.md`.
2. Preserve the collection/output separation.
   Do not blur one-shot data fetching into read-side output paths without a strong reason.
3. Prefer small, buildable changes.
   Each step should leave the repo in a coherent, working state.
4. Keep persistence and scaling behavior in mind.
   For collection changes, consider large-drive behavior, interruption, retries, and partial-failure handling.
5. Keep output semantics consistent across formats.
   If path or permissions formatting changes in one output, check whether the same concept should change elsewhere too.
6. Run local checks after changes using the checks that actually exist in the repo.
   If a previously expected check does not exist, do not invent one; run the closest available verification and note any gaps.
7. Do not introduce new dependencies without stating:
   - why the dependency is needed
   - alternatives considered
   - ongoing maintenance cost

## Change Discipline

- Prefer multiple small commits with clear messages when making larger changes.
- Update docs when behavior, CLI shape, storage behavior, or output semantics change.
- Keep naming consistent across CLI help, code, tests, and docs.

## Security And Privacy

- Do not log potentially sensitive payloads by default.
- Avoid embedding identifiers beyond what the tool intentionally emits.
- Treat permissions and path metadata as potentially sensitive when deciding what to print automatically.
