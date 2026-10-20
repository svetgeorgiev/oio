# OIO v0.4 — remove original demonstration data

Stop OIO's **Python backend** before running the cleaner. This tool removes the **five exact v0.1 fixture posts** and their known synthetic cluster plus linked test investigation. It does not delete live Bluesky posts, session logs, unrelated investigations, or unrelated reference records.

This **also removes the linked synthetic test investigation**, its reviewer notes, audit events and any manually attached evidence items. A full SQLite backup (including current WAL contents) is created and validated **outside** `D:\WebstormProjects\oio`, under `D:\WebstormProjects\oio-backups` by default. Since the backup includes live user content, keep it private and delete it under your data retention rules after you no longer need it.

From WebStorm PowerShell (project root):

```powershell
python backend\clear_demo_data.py
```

This is a **dry run**, nothing is removed. Read the output carefully.

```powershell
python backend\clear_demo_data.py --apply
```

Type `DELETE DEMO DATA` when prompted. The cleanup is transactional and verifies a database backup first.

Restart the backend, then refresh the browser. The v0.1 synthetic cluster should disappear; your previously captured public Bluesky posts should remain. No live cluster is guaranteed to appear because v0.4 requires exact text matching from three separate actors within 180 seconds.

The fixture and `Load demo data` controls **remain available** for reproducible development tests. Avoid clicking that button again. We can hide it behind an explicit developer mode in the next app patch. Running the utility again is safe and should find nothing to remove.

If something unexpected happens, **do not overwrite the working database**. Stop the backend, locate the timestamped `.sqlite3` backup printed by the tool, and recover after confirming the correct source database and SQLite WAL state.
