"""Opt-in Meta Cloud API template adapter. Provider acceptance is not delivery."""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

LAST_CHECK = None
FIELDS = ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_API_VERSION", "WHATSAPP_TEMPLATE_NAME", "WHATSAPP_TEMPLATE_LANGUAGE")


def configuration():
    values = {key: os.getenv(key, "").strip() for key in FIELDS}
    missing = [key for key, value in values.items() if not value]
    valid = not missing and bool(re.fullmatch(r"[0-9]{5,30}", values["WHATSAPP_PHONE_NUMBER_ID"]) and
        re.fullmatch(r"v[0-9]{1,2}\.0", values["WHATSAPP_API_VERSION"]) and
        re.fullmatch(r"[a-z][a-z0-9_]{0,99}", values["WHATSAPP_TEMPLATE_NAME"]) and
        re.fullmatch(r"[a-z]{2}(?:_[A-Z]{2})?", values["WHATSAPP_TEMPLATE_LANGUAGE"]))
    return values, missing, valid


def status():
    _, missing, valid = configuration()
    enabled = os.getenv("BIGBEN_WHATSAPP_ENABLED", "0") == "1"
    return {"enabled": enabled, "credentials_configured": bool(valid), "missing_settings": missing,
            "state": "DISABLED" if not enabled else "READY_UNVERIFIED" if valid else "NOT_CONFIGURED",
            "provider_connection_verified": bool(LAST_CHECK and LAST_CHECK["state"] == "ACCEPTED"),
            "delivery_verified": False, "last_check": LAST_CHECK.copy() if LAST_CHECK else None}


def send_template(recipient, parameters):
    """The approved template must have nine positional BODY text parameters."""
    global LAST_CHECK
    if os.getenv("BIGBEN_WHATSAPP_ENABLED", "0") != "1": return "disabled"
    values, _, valid = configuration()
    if not valid: return "not_configured"
    if not isinstance(recipient, str) or not re.fullmatch(r"\+[1-9][0-9]{6,14}", recipient): return "recipient_required"
    if not isinstance(parameters, list) or len(parameters) != 9 or any(not isinstance(p, str) or not p or len(p)>512 for p in parameters): return "invalid_template_parameters"
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient[1:],
        "type": "template", "template": {"name": values["WHATSAPP_TEMPLATE_NAME"],
        "language": {"code": values["WHATSAPP_TEMPLATE_LANGUAGE"]},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in parameters]}]}}
    request = urllib.request.Request("https://graph.facebook.com/"+values["WHATSAPP_API_VERSION"]+"/"+values["WHATSAPP_PHONE_NUMBER_ID"]+"/messages",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer "+values["WHATSAPP_ACCESS_TOKEN"]}, method="POST")
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(16385)
            if response.status != 200 or len(raw)>16384: raise ValueError()
            data = json.loads(raw)
            messages = data.get("messages") if isinstance(data, dict) else None
            if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict) or not isinstance(messages[0].get("id"), str) or not messages[0]["id"]: raise ValueError()
        LAST_CHECK = {"state": "ACCEPTED", "checked_at": stamp, "delivery_verified": False}
        return "accepted"
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        LAST_CHECK = {"state": "UNAVAILABLE", "checked_at": stamp, "http_status": code}
        return "provider_http_"+str(code)
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        LAST_CHECK = {"state": "UNAVAILABLE", "checked_at": stamp}
        return "provider_unavailable"
