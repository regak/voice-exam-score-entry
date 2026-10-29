"""Typed command schema for parsed voice commands.

These dataclasses represent the *result* of parsing a transcript into a
structured, validated-shape command. They do NOT perform business
validation (e.g. score range checks) - that happens in src/validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union


class CommandType(str, Enum):
    SET_SCORE = "set_score"
    SET_GENDER = "set_gender"
    SET_FULL_NAME = "set_full_name"
    FIND_BY_REGISTRATION = "find_by_registration"
    FIND_BY_NAME = "find_by_name"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True)
class SetScoreCommand:
    registration_number: str
    score_text: str  # raw text form of the number, validated later
    type: CommandType = CommandType.SET_SCORE


@dataclass(frozen=True)
class SetGenderCommand:
    registration_number: str
    gender_text: str
    type: CommandType = CommandType.SET_GENDER


@dataclass(frozen=True)
class SetFullNameCommand:
    registration_number: str
    full_name: str
    type: CommandType = CommandType.SET_FULL_NAME


@dataclass(frozen=True)
class FindByRegistrationCommand:
    registration_number: str
    type: CommandType = CommandType.FIND_BY_REGISTRATION


@dataclass(frozen=True)
class FindByNameCommand:
    full_name: str
    type: CommandType = CommandType.FIND_BY_NAME


@dataclass(frozen=True)
class UnrecognizedCommand:
    raw_text: str
    reason: str
    type: CommandType = CommandType.UNRECOGNIZED


Command = Union[
    SetScoreCommand,
    SetGenderCommand,
    SetFullNameCommand,
    FindByRegistrationCommand,
    FindByNameCommand,
    UnrecognizedCommand,
]
