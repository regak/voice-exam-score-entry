"""Audit logging for successful changes and errors.

Appends JSON Lines records. Never stores raw audio or secrets.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AuditRecord:
    timestamp: str
    event: str  # "update" | "error"
    candidate_identifier: str
    cell: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    message: str = ""


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_update(
        self,
        candidate_identifier: str,
        cell: str,
        old_value,
        new_value,
        message: str = "",
    ) -> None:
        record = AuditRecord(
            timestamp=_now_iso(),
            event="update",
            candidate_identifier=candidate_identifier,
            cell=cell,
            old_value=_safe_str(old_value),
            new_value=_safe_str(new_value),
            message=message,
        )
        self._append(record)

    def log_error(
        self,
        candidate_identifier: str,
        message: str,
        cell: Optional[str] = None,
        old_value=None,
        new_value=None,
    ) -> None:
        record = AuditRecord(
            timestamp=_now_iso(),
            event="error",
            candidate_identifier=candidate_identifier,
            cell=cell,
            old_value=_safe_str(old_value),
            new_value=_safe_str(new_value),
            message=message,
        )
        self._append(record)

    def _append(self, record: AuditRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value) -> Optional[str]:
    if value is None:
        return None
    return str(value)
