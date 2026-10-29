"""Application-wide configuration loading.

Loads non-secret configuration from config.json and exposes a typed
AppConfig object. No secrets (API keys, passwords) should ever live here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ExcelColumnsConfig:
    registration_number: str = "B"
    full_name: str = "C"
    gender: str = "D"
    score: str = "E"


@dataclass
class ExcelConfig:
    workbook_path: Optional[str] = None
    worksheet_name: Optional[str] = None
    header_row: int = 1
    columns: ExcelColumnsConfig = field(default_factory=ExcelColumnsConfig)
    treat_registration_number_as_text: bool = True


@dataclass
class ValidationConfig:
    score_min: float = 0
    score_max: float = 60
    accepted_genders: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SpeechConfig:
    whisper_model_size: str = "base"
    language: str = "en"
    push_to_talk_key: str = "F8"
    sample_rate: int = 16000


@dataclass
class ConfirmationConfig:
    require_confirmation: bool = True


@dataclass
class AuditLogConfig:
    path: str = "logs/audit_log.jsonl"
    store_raw_audio: bool = False


@dataclass
class AppConfig:
    excel: ExcelConfig = field(default_factory=ExcelConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    confirmation: ConfirmationConfig = field(default_factory=ConfirmationConfig)
    audit_log: AuditLogConfig = field(default_factory=AuditLogConfig)

    @staticmethod
    def load(path: str | Path = "config.json") -> "AppConfig":
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        excel_raw = raw.get("excel", {})
        columns_raw = excel_raw.get("columns", {})
        excel = ExcelConfig(
            workbook_path=excel_raw.get("workbook_path"),
            worksheet_name=excel_raw.get("worksheet_name"),
            header_row=excel_raw.get("header_row", 1),
            columns=ExcelColumnsConfig(
                registration_number=columns_raw.get("registration_number", "B"),
                full_name=columns_raw.get("full_name", "C"),
                gender=columns_raw.get("gender", "D"),
                score=columns_raw.get("score", "E"),
            ),
            treat_registration_number_as_text=excel_raw.get(
                "treat_registration_number_as_text", True
            ),
        )

        validation_raw = raw.get("validation", {})
        validation = ValidationConfig(
            score_min=validation_raw.get("score_min", 0),
            score_max=validation_raw.get("score_max", 60),
            accepted_genders=validation_raw.get("accepted_genders", {}),
        )

        speech_raw = raw.get("speech", {})
        speech = SpeechConfig(
            whisper_model_size=speech_raw.get("whisper_model_size", "base"),
            language=speech_raw.get("language", "en"),
            push_to_talk_key=speech_raw.get("push_to_talk_key", "F8"),
            sample_rate=speech_raw.get("sample_rate", 16000),
        )

        confirmation_raw = raw.get("confirmation", {})
        confirmation = ConfirmationConfig(
            require_confirmation=confirmation_raw.get("require_confirmation", True)
        )

        audit_raw = raw.get("audit_log", {})
        audit_log = AuditLogConfig(
            path=audit_raw.get("path", "logs/audit_log.jsonl"),
            store_raw_audio=audit_raw.get("store_raw_audio", False),
        )

        return AppConfig(
            excel=excel,
            validation=validation,
            speech=speech,
            confirmation=confirmation,
            audit_log=audit_log,
        )
