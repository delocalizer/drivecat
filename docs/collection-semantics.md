## Collection Semantics

This note documents how `drivecat collect` handles folder traversal, partial reads,
and the persistent folder queue stored in SQLite.

### Folder processing model

Collection is folder-by-folder. For each queued folder, the collector asks `gws`
for that folder's direct children and stages the returned items in memory before
writing them into the database.

This gives collection folder-level atomicity:

- If a folder listing completes successfully, its child items and child edges are
  committed to SQLite.
- If a folder listing fails after returning only some children, those partial
  children are discarded and not committed.
- A failed folder is recorded as a collection error and treated as a skipped
  subtree.

In other words, `drivecat` does not persist partial contents for a folder whose
listing terminates with an error.

### Retry behavior

The `gws` wrapper retries transient errors, but only before any child records
have been yielded for the current folder listing.

- Failures before the first yielded child may be retried.
- Failures after one or more children have already been yielded are not retried
  at the `gws` layer.
- When that later failure reaches the collector, the collector drops the staged
  partial folder contents and records a folder-level error instead.

This avoids mixing retry logic with partially consumed paginated output.

### Folder queue

Traversal state is persisted in the `folder_queue` SQLite table. Each discovered
folder is tracked in one of three states:

- `pending`: discovered but not yet processed
- `processing`: currently being listed
- `done`: processed successfully, or failed and recorded as an error

The queue lets collection continue incrementally without keeping the full
traversal worklist only in memory. When a folder is processed successfully, any
child folders discovered in that listing are enqueued as new `pending` work.

### What the queue does not do

The queue is persistent within a run, but it is not currently used as a
cross-run resume mechanism.

Each new `collect` invocation reinitializes the target database and clears the
existing queue and collected data before starting from the requested root again.
That means:

- interrupted runs are not resumed from the existing SQLite file
- folders left in `pending` or `processing` from an interrupted run are not reused
- recovery is at the level of retrying transient API failures within the same run,
  not resuming a previously interrupted traversal

### Output implications

Collection errors are stored separately from item records. Output commands can
still render the successfully collected portion of the tree or record stream, and
they report the number of recorded collection errors as a warning.
