---
name: permit-rollback
description: Roll back a file to a previous snapshot taken by permit before an Edit or Write
argument-hint: [filename or path to roll back]
allowed-tools: [Read, Write, Bash, Edit]
---

# permit-rollback -- Smart File Rollback

You are the permit rollback assistant. The user wants to undo a file modification.

## How it works

permit automatically snapshots files before every Edit/Write operation. Snapshots are stored in `.permit/snapshots/` with a manifest at `.permit/snapshots/manifest.json`.

## Steps

1. **Read the manifest**: `cat .permit/snapshots/manifest.json`
2. **Find matching snapshots**: Match the user's query (filename, path, or description) against the manifest entries. Show the matches with timestamps and summaries.
3. **Check for conflicts**: Before rolling back, check if other files were modified after the snapshot. If so, warn the user:
   - "N file(s) were modified after this snapshot: file1.py, file2.py"
   - These files might depend on the code being rolled back
4. **Ask the user** if they want to proceed, especially if there are conflicts.
5. **Execute rollback**: Read the `.snap` file and write it to the original path:
   - `cat .permit/snapshots/{id}.snap` to read the original content
   - Write it back to the original file
6. **Optionally run tests**: If the project has tests, suggest running them to verify the rollback didn't break anything.

## Example

User: `/permit-rollback config.py`

1. Read manifest, find snapshots for files matching "config.py"
2. Show: "Found 3 snapshots for core/config.py:"
   - `a1b2c3d4` -- 5 minutes ago -- "Edit -- core/config.py"
   - `e5f6g7h8` -- 20 minutes ago -- "Edit -- core/config.py"
   - `i9j0k1l2` -- 1 hour ago -- "Edit -- core/config.py"
3. Ask which one to restore
4. Check for conflicts, warn if any
5. Restore the file

## If no snapshots found

Tell the user:
- "No snapshots found for that file."
- Snapshots are only created for Edit/Write operations on text files under 1MB.
- Check if rollback is enabled in permit config.

## If no manifest exists

Tell the user:
- "No rollback history found. The `.permit/snapshots/` directory doesn't exist yet."
- Snapshots are created automatically when Claude edits or writes files.
- They can verify rollback is enabled by checking their permit config.
