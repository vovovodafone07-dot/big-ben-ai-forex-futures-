"""Private recipient preferences and delivery receipts. No API secrets stored here."""
import json
import re
from datetime import datetime, timezone


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS notification_preferences (id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS notification_deliveries (id TEXT PRIMARY KEY,event_id TEXT NOT NULL,channel TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL)")


def read(connection):
    row = connection.execute("SELECT payload FROM notification_preferences WHERE id='owner'").fetchone()
    return json.loads(row[0]) if row else {"telegram_chat_id": "", "whatsapp_number": "", "watchlist": []}


def validate(value, normalize):
    if not isinstance(value, dict) or set(value)-{"telegram_chat_id", "whatsapp_number", "watchlist"}: raise ValueError("settings")
    chat = value.get("telegram_chat_id", "")
    phone = value.get("whatsapp_number", "")
    watchlist = value.get("watchlist", [])
    if not isinstance(chat, str) or not isinstance(phone, str): raise ValueError("recipient")
    chat, phone = chat.strip(), phone.strip().replace(" ", "").replace("-", "")
    if chat and not re.fullmatch(r"-?[0-9]{5,20}", chat): raise ValueError("telegram_chat_id_required_not_phone")
    if phone and not re.fullmatch(r"\+[1-9][0-9]{6,14}", phone): raise ValueError("whatsapp_e164_required")
    if not isinstance(watchlist, list) or len(watchlist)>500: raise ValueError("watchlist_limit_500")
    symbols = list(dict.fromkeys(normalize(s) for s in watchlist))
    return {"telegram_chat_id": chat, "whatsapp_number": phone, "watchlist": symbols}


def save(connection, value, postgres=False):
    marker = "%s" if postgres else "?"
    connection.execute("INSERT INTO notification_preferences(id,payload) VALUES ('owner',"+marker+") ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (json.dumps(value),))


def receipt(connection, event_id, channel, status, postgres=False):
    marker = "%s" if postgres else "?"
    connection.execute("INSERT INTO notification_deliveries(id,event_id,channel,status,created_at) VALUES ("+",".join([marker]*5)+") ON CONFLICT(id) DO NOTHING",
                       (event_id+":"+channel, event_id, channel, status, datetime.now(timezone.utc).isoformat()))


def recent(connection):
    return [{"event_id": row[0], "channel": row[1], "status": row[2], "created_at": row[3]} for row in connection.execute("SELECT event_id,channel,status,created_at FROM notification_deliveries ORDER BY created_at DESC LIMIT 30").fetchall()]
