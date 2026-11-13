"""Additive event migration; existing rows keep unknown receipt times as NULL."""
def migrate_events(connection, postgres=False):
    if postgres:
        connection.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS received_at TEXT")
    else:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        if "received_at" not in columns:
            connection.execute("ALTER TABLE events ADD COLUMN received_at TEXT")
    connection.execute("CREATE INDEX IF NOT EXISTS events_symbol_time_idx ON events(symbol,time)")
    connection.execute("CREATE INDEX IF NOT EXISTS events_kind_time_idx ON events(event,time)")
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
    if postgres:
        connection.execute("INSERT INTO schema_migrations(version) VALUES ('001_event_receipt') ON CONFLICT DO NOTHING")
    else:
        connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES ('001_event_receipt')")
