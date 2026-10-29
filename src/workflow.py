"""Orchestration layer: ties together parsing, candidate lookup,
validation, and the spreadsheet backend into a single safe workflow.

This module intentionally contains no UI or speech code so it can be
unit-tested headlessly and reused by the desktop UI in later stages.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.candidates.lookup import LookupStatus, find_by_full_name, find_by_registration_number
from src.candidates.models import Candidate
from src.commands.parser import parse_command
from src.commands.schema import (
    Command,
    CommandType,
    FindByNameCommand,
    FindByRegistrationCommand,
    SetFullNameCommand,
    SetGenderCommand,
    SetScoreCommand,
    UnrecognizedCommand,
)
from src.config import AppConfig
from src.spreadsheets.base import SpreadsheetBackend, SpreadsheetError
from src.validation.audit_log import AuditLog
from src.validation.rules import validate_full_name, validate_gender, validate_score


class ProcessingOutcome(str, Enum):
    NEEDS_CONFIRMATION = "needs_confirmation"
    INFO_ONLY = "info_only"  # e.g. a "find" command with nothing to confirm
    REJECTED = "rejected"  # could not parse / validate / find candidate


@dataclass(frozen=True)
class ProposedUpdate:
    candidate: Candidate
    column_letter: str
    field_name: str
    old_value: object
    new_value: object


@dataclass(frozen=True)
class ProcessingResult:
    outcome: ProcessingOutcome
    raw_text: str
    command: Command
    message: str
    candidate: Optional[Candidate] = None
    matches: tuple = ()
    proposed_update: Optional[ProposedUpdate] = None


def process_transcript(
    raw_text: str, candidates: list[Candidate], config: AppConfig
) -> ProcessingResult:
    """Parse a transcript and figure out what (if anything) should
    happen next, WITHOUT writing to the spreadsheet. The caller must
    separately confirm and call apply_update() to actually write.
    """
    command = parse_command(raw_text)

    if isinstance(command, UnrecognizedCommand):
        return ProcessingResult(
            outcome=ProcessingOutcome.REJECTED,
            raw_text=raw_text,
            command=command,
            message=f"Could not understand command: {command.reason}",
        )

    if isinstance(command, FindByRegistrationCommand):
        result = find_by_registration_number(candidates, command.registration_number)
        return _lookup_to_find_result(raw_text, command, result)

    if isinstance(command, FindByNameCommand):
        result = find_by_full_name(candidates, command.full_name)
        return _lookup_to_find_result(raw_text, command, result)

    if isinstance(
        command, (SetScoreCommand, SetGenderCommand, SetFullNameCommand)
    ):
        lookup_result = find_by_registration_number(
            candidates, command.registration_number
        )
        if lookup_result.status == LookupStatus.NOT_FOUND:
            return ProcessingResult(
                outcome=ProcessingOutcome.REJECTED,
                raw_text=raw_text,
                command=command,
                message=lookup_result.message,
            )
        if lookup_result.status == LookupStatus.AMBIGUOUS:
            return ProcessingResult(
                outcome=ProcessingOutcome.REJECTED,
                raw_text=raw_text,
                command=command,
                message=lookup_result.message,
                matches=lookup_result.matches,
            )

        candidate = lookup_result.candidate

        if isinstance(command, SetScoreCommand):
            validation = validate_score(
                command.score_text,
                config.validation.score_min,
                config.validation.score_max,
            )
            if not validation.is_valid:
                return ProcessingResult(
                    outcome=ProcessingOutcome.REJECTED,
                    raw_text=raw_text,
                    command=command,
                    message=validation.error_message,
                    candidate=candidate,
                )
            proposed = ProposedUpdate(
                candidate=candidate,
                column_letter=config.excel.columns.score,
                field_name="score",
                old_value=candidate.score,
                new_value=validation.normalized_value,
            )
        elif isinstance(command, SetGenderCommand):
            validation = validate_gender(
                command.gender_text, config.validation.accepted_genders
            )
            if not validation.is_valid:
                return ProcessingResult(
                    outcome=ProcessingOutcome.REJECTED,
                    raw_text=raw_text,
                    command=command,
                    message=validation.error_message,
                    candidate=candidate,
                )
            proposed = ProposedUpdate(
                candidate=candidate,
                column_letter=config.excel.columns.gender,
                field_name="gender",
                old_value=candidate.gender,
                new_value=validation.normalized_value,
            )
        else:  # SetFullNameCommand
            validation = validate_full_name(command.full_name)
            if not validation.is_valid:
                return ProcessingResult(
                    outcome=ProcessingOutcome.REJECTED,
                    raw_text=raw_text,
                    command=command,
                    message=validation.error_message,
                    candidate=candidate,
                )
            proposed = ProposedUpdate(
                candidate=candidate,
                column_letter=config.excel.columns.full_name,
                field_name="full_name",
                old_value=candidate.full_name,
                new_value=validation.normalized_value,
            )

        return ProcessingResult(
            outcome=ProcessingOutcome.NEEDS_CONFIRMATION,
            raw_text=raw_text,
            command=command,
            message=(
                f"Proposed update for {candidate.full_name} "
                f"({candidate.registration_number}): "
                f"{proposed.field_name} '{proposed.old_value}' -> "
                f"'{proposed.new_value}'."
            ),
            candidate=candidate,
            proposed_update=proposed,
        )

    return ProcessingResult(
        outcome=ProcessingOutcome.REJECTED,
        raw_text=raw_text,
        command=command,
        message="Unhandled command type.",
    )


def _lookup_to_find_result(raw_text: str, command: Command, result) -> ProcessingResult:
    if result.status == LookupStatus.FOUND:
        return ProcessingResult(
            outcome=ProcessingOutcome.INFO_ONLY,
            raw_text=raw_text,
            command=command,
            message=result.message,
            candidate=result.candidate,
            matches=result.matches,
        )
    outcome = (
        ProcessingOutcome.REJECTED
    )  # not found or ambiguous: nothing to confirm, surface message
    return ProcessingResult(
        outcome=outcome,
        raw_text=raw_text,
        command=command,
        message=result.message,
        matches=result.matches,
    )


def apply_update(
    proposed: ProposedUpdate,
    backend: SpreadsheetBackend,
    audit_log: AuditLog,
) -> ProcessingResult:
    """Write a confirmed proposed update to the backend and record the
    result in the audit log. Caller MUST have already obtained explicit
    user confirmation before calling this.
    """
    candidate_identifier = (
        f"{proposed.candidate.registration_number} ({proposed.candidate.full_name})"
    )
    try:
        backend.write_cell(
            proposed.candidate.row_number,
            proposed.column_letter,
            proposed.new_value,
        )
    except SpreadsheetError as exc:
        audit_log.log_error(
            candidate_identifier=candidate_identifier,
            message=str(exc),
            cell=f"{proposed.column_letter}{proposed.candidate.row_number}",
            old_value=proposed.old_value,
            new_value=proposed.new_value,
        )
        return ProcessingResult(
            outcome=ProcessingOutcome.REJECTED,
            raw_text="",
            command=UnrecognizedCommand(raw_text="", reason=""),
            message=f"Failed to write update: {exc}",
            candidate=proposed.candidate,
        )

    audit_log.log_update(
        candidate_identifier=candidate_identifier,
        cell=f"{proposed.column_letter}{proposed.candidate.row_number}",
        old_value=proposed.old_value,
        new_value=proposed.new_value,
        message=f"Updated {proposed.field_name}.",
    )
    return ProcessingResult(
        outcome=ProcessingOutcome.INFO_ONLY,
        raw_text="",
        command=UnrecognizedCommand(raw_text="", reason=""),
        message=(
            f"Updated {proposed.field_name} for {proposed.candidate.full_name} "
            f"({proposed.candidate.registration_number}) to "
            f"'{proposed.new_value}'."
        ),
        candidate=proposed.candidate,
    )
