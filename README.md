# drivecat

`drivecat` is a minimal command-line tool that does two things:

1. collects structure and metadata of a Google Drive folder contents into a local SQLite database
2. outputs the folder structure and metadata in one of several formats

## Motivation
As a document manager / auditor / security professional I want to understand the structure and permissions of Google Drive (“GDrive”) locations under my care. For example, I want to know:
* Who owns certain documents
* Which documents are open to the world
* Which documents are / are not visible by a user or group
* How many documents live in a folder and its subfolders
* What redundancies exist in permissions — e.g. do some users have access to a document both as an individual, and as a member of a group


## Features

- Collect one root folder and all reachable descendant folders/files
- Persist collected data locally in SQLite
- Write tree, TSV, or NDJSON output from the persisted data without talking to Google Drive

### Runtime validation & error handling
- Validate the installed `gws` version before collecting
- Detect when `gws` pagination stops at the configured page limit instead of silently truncating a folder listing
- Record per-folder collection failures instead of aborting the whole run
- Retry transient Drive and transport failures with backoff

## Requirements

- Python 3.11+
- [`gws`](https://github.com/googleworkspace/cli) on `PATH`
- Authenticated `gws` session with Drive access

Quick check:

```bash
gws --version
gws drive files list --params '{"pageSize": 1}'
```

## Usage

Run directly from the repo:

```bash
PYTHONPATH=src python3 -m drivecat collect out/drive.sqlite3 --root-id root
PYTHONPATH=src python3 -m drivecat output out/drive.sqlite3 --format tree
```

Or install locally as a script:

```bash
python3 -m pip install -e .
drivecat collect out/drive.sqlite3 --root-id root
drivecat output out/drive.sqlite3 --format tree
```

Tune the per-folder pagination cap if needed:

```bash
drivecat collect out/drive.sqlite3 --root-id root --page-limit 20000
```

Print progress periodically during large runs:

```bash
drivecat collect out/drive.sqlite3 --root-id root --checkpoint-every 250
```

Render folders only:

```bash
drivecat output out/drive.sqlite3 --format tree --folders-only
```

Limit display depth:

```bash
drivecat output out/drive.sqlite3 --format tree -L 2
```

Write TSV to stdout:

```bash
drivecat output out/drive.sqlite3 --format tsv
```

Write NDJSON to stdout:

```bash
drivecat output out/drive.sqlite3 --format ndjson
```

## SQLite Output

The primary artifact produced by `collect` is a SQLite database containing:

- root metadata
- normalized item metadata
- parent/child relationships
- traversal queue state
- per-folder collection errors

## Output Formats

`output --format tree` writes a box-drawing tree to stdout.
Each tree line includes:

- the object name
- a trailing `/` for folders
- a square-bracketed permissions annotation

The tree-specific options are:

- `--folders-only`
- `-L` / `--depth`

`output --format ndjson` writes one self-contained record per reachable item.
Each NDJSON line includes:

- the full user-readable path
- the path segments
- the depth from the requested root
- all collected item metadata

The `path` field uses a rooted user-readable form such as:

- `MyDrive:/`
- `MyDrive:/folder1/folder2/myfile.txt`

The `permissions` value used by `output --format tsv` is the same square-bracketed annotation shown in tree output.
The TSV columns are:

- `path`
- `permissions`

Collected metadata includes:

- name
- mime type
- parent IDs
- drive ID
- owners
- permissions
- size
- modified time
- web view link

## Notes and limitations

- The collector walks the tree by listing each folder's direct children. It streams paginated `gws` pages folder-by-folder from subprocess stdout and keeps collection state in a local SQLite database during traversal.
- Google Drive items can have multiple parents in some edge cases. Tree output treats the collected parent-child structure as a tree rooted at the requested folder.
- Shared drives are supported through `supportsAllDrives` and `includeItemsFromAllDrives`, but this has only been wired for the basic traversal path.
- The collector retries transient API and transport failures with exponential backoff. Permanent permission failures produce skipped-subtree errors.
- The SQLite database written to `--output` is the primary artifact.
- `output --format tsv` and `output --format ndjson` stream records from SQLite and avoid materializing one giant snapshot document in memory.
- `gws` version `0.22.0` or newer is required. The tool checks this at startup.
- The Python implementation uses only the standard library.

## Development

Run local checks:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall src
python3 -m py_compile src/drivecat/*.py
```
