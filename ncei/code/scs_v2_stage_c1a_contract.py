#!/usr/bin/env python3
"""Frozen Stage C.1a atomic handling for missing or invalid sounding time."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ncei.code.scs_v2_stage_c1_contract import join_all_and_good, parse_mblist_tsv


TIME_FAILURE_STATUS = "failed_invalid_or_missing_time"
PARSER_FAILURE_STATUS = "failed_parser_contract"
PASS_STATUS = "pass"


@dataclass(frozen=True)
class AtomicStreamOutcome:
    parse_status: str
    parsed_row_count: int
    soundings: tuple[dict[str, object], ...]
    error_code: str | None
    error_detail: str | None
    time_utc_field_available: bool
    time_utc_field_status: str
    time_utc_evidence_kind: str


def _time_failure(text: str, stream_name: str) -> tuple[str, str] | None:
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        fields = raw_line.split("\t")
        if len(fields) != 7:
            continue
        value = fields[0].strip()
        if not value:
            return "TIME_UTC_MISSING", f"{stream_name} line {line_number} has an empty M field"
        try:
            epoch = Decimal(value)
        except InvalidOperation:
            return "TIME_UTC_INVALID", f"{stream_name} line {line_number} has a nonnumeric M field"
        if not epoch.is_finite() or epoch < 0:
            return "TIME_UTC_INVALID", f"{stream_name} line {line_number} has an invalid Unix epoch"
    return None


def parse_source_streams_atomically(
    acquisition_run_id: str,
    source_object_relative_path: str,
    all_u3_text: str,
    good_u0_text: str,
) -> AtomicStreamOutcome:
    """Parse both streams fully or emit no sounding rows for the object."""
    for stream_name, text in (("U3", all_u3_text), ("U0", good_u0_text)):
        failure = _time_failure(text, stream_name)
        if failure is not None:
            error_code, error_detail = failure
            return AtomicStreamOutcome(
                parse_status=TIME_FAILURE_STATUS,
                parsed_row_count=0,
                soundings=(),
                error_code=error_code,
                error_detail=error_detail,
                time_utc_field_available=False,
                time_utc_field_status="known",
                time_utc_evidence_kind="parser_preflight_failure",
            )

    try:
        all_rows = parse_mblist_tsv(all_u3_text, check_mode=3)
        good_rows = parse_mblist_tsv(good_u0_text, check_mode=0)
        soundings = join_all_and_good(
            acquisition_run_id,
            source_object_relative_path,
            all_rows,
            good_rows,
        )
    except ValueError as error:
        return AtomicStreamOutcome(
            parse_status=PARSER_FAILURE_STATUS,
            parsed_row_count=0,
            soundings=(),
            error_code="PARSER_CONTRACT_FAILURE",
            error_detail=str(error),
            time_utc_field_available=False,
            time_utc_field_status="known",
            time_utc_evidence_kind="parser_preflight_failure",
        )

    return AtomicStreamOutcome(
        parse_status=PASS_STATUS,
        parsed_row_count=len(soundings),
        soundings=tuple(soundings),
        error_code=None,
        error_detail=None,
        time_utc_field_available=True,
        time_utc_field_status="verified_from_source_metadata",
        time_utc_evidence_kind="decoded_format58_M_field",
    )
