"""IrohaWalendar-compatible v5 snapshot validation."""

from __future__ import annotations

from typing import Any

from .security import ValidationError, compact_json_size
from .storage import PLANNER_MAX_BYTES


LIST_LIMITS = {
    "goals": 500,
    "actions": 5_000,
    "routineCategories": 500,
    "routines": 5_000,
    "plans": 100_000,
    "completionRecords": 100_000,
}
SYNCED_SETTINGS = {
    "theme",
    "statsPeriod",
    "statsMode",
    "calendarZoom",
    "dayStartMinute",
    "dayEndMinute",
    "timeDivisionMode",
    "timeDivisionInterval",
    "timeDivisionPoints",
    "calendarSelectionEnabled",
}


def validate_planner_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("invalid_planner", "规划快照必须是 JSON 对象。")
    if value.get("version") != 5:
        raise ValidationError("unsupported_planner_version", "仅接受 IrohaWalendar v5 快照。")
    revision = value.get("revision")
    if not isinstance(revision, int) or revision <= 0:
        raise ValidationError("invalid_planner_revision", "规划快照必须带递增的正整数 revision。")
    source_updated_at = value.get("source_updated_at")
    if not isinstance(source_updated_at, str) or len(source_updated_at) > 40:
        raise ValidationError("invalid_planner_timestamp", "规划快照缺少有效的 source_updated_at。")
    for key, limit in LIST_LIMITS.items():
        items = value.get(key)
        if not isinstance(items, list):
            raise ValidationError("invalid_planner", f"规划快照缺少有效的 {key} 列表。")
        if len(items) > limit or any(not isinstance(item, dict) for item in items):
            raise ValidationError("planner_limit_exceeded", f"{key} 条目无效或超过 {limit} 条限制。")
    if not isinstance(value.get("settings"), dict):
        raise ValidationError("invalid_planner", "规划 settings 必须是对象。")
    allowed = set(LIST_LIMITS) | {"version", "revision", "source_updated_at", "received_at", "settings"}
    if set(value) - allowed:
        raise ValidationError("unknown_planner_field", "规划快照包含不支持的顶层字段。")
    sanitized = dict(value)
    sanitized["settings"] = {key: item for key, item in value["settings"].items() if key in SYNCED_SETTINGS}
    if compact_json_size(sanitized) > PLANNER_MAX_BYTES:
        raise ValidationError("planner_too_large", "规划快照超过 12 MiB 限制。")
    return sanitized


__all__ = ["validate_planner_snapshot"]
