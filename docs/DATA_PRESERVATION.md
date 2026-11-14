# Application data preservation

The private Settings page exports a consistent application-data snapshot from17 named tables. It includes events, candles, research and replay runs, analysis runs, drafts, notes, daily reports and destination settings. It excludes environment secrets, transient job leases and Render infrastructure/database roles. Export is authenticated, single-concurrency, bounded to100000rows/32MiB, and fails entirely rather than returning a partial successful archive. Each table has a SHA256 checksum. Keep the exported file private because it contains owner notes and destination settings.

Verify an exported file:

```powershell
python scripts/restore_application_backup.py PATH_TO_EXPORT.json
```

Restore into a NEW local SQLite file (never an existing database):

```powershell
python scripts/restore_application_backup.py PATH_TO_EXPORT.json --new-sqlite NEW_LOCAL_COPY.sqlite3
```

The restore tool clears production database selection in its own process, validates checksums/schema, refuses overwrite and nonempty targets, and restores with parameterized statements. It never connects to production. There is no HTTP restore endpoint. SQLite round-trip tests and isolated PostgreSQL-to-SQLite CI cover preservation. Actual production export/download verification is a separate milestone. This is not a full PostgreSQL roles/schema/infrastructure backup, nor an automatically scheduled offsite backup or completed migration.

Current free PostgreSQL expiry:11December2026. Saving and verifying an application export preserves its rows, but an external hosting migration or database renewal must still be completed before expiry. Do not open database external IP access or purchase a paid plan without the appropriate scope.
