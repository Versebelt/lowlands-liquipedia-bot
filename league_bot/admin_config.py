"""Persistent Discord-backed configuration for the Lowlands League bot."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass


CONFIG_CHANNEL_NAME = "lowlands-bot-config"
TOPIC_PREFIX = "LLBOT_CONFIG_V1:"


@dataclass
class AdminConfig:
    announcement_channel_id: str = ""
    reminder_role_id: str = ""
    reminders_enabled: bool = True
    monday_time: str = "09:00"
    friday_time: str = "20:00"
    sunday_time: str = "10:00"
    timezone: str = "Europe/Amsterdam"


def encode_topic(config: AdminConfig) -> str:
    raw = json.dumps(asdict(config), separators=(",", ":"), sort_keys=True).encode()
    token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return TOPIC_PREFIX + token


def decode_topic(topic: str | None) -> AdminConfig | None:
    value = str(topic or "")
    if not value.startswith(TOPIC_PREFIX):
        return None
    token = value[len(TOPIC_PREFIX) :]
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        data = json.loads(raw.decode())
        return AdminConfig(**{key: data[key] for key in AdminConfig.__dataclass_fields__ if key in data})
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def valid_time(value: str) -> bool:
    parts = value.strip().split(":")
    return len(parts) == 2 and all(part.isdigit() for part in parts) and 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59
