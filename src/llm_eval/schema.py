"""Focused validation for the versioned car-decision output contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return "{}: {}".format(self.path, self.message)


TOP_LEVEL_FIELDS = {
    "turn_summary",
    "effective_constraints",
    "candidate_cars",
    "final_recommendation",
    "next_question",
    "confidence",
    "status",
    "assumptions",
}
CONSTRAINT_FIELDS = {"name", "value", "source_turn", "status"}
CANDIDATE_FIELDS = {
    "model",
    "trim",
    "year",
    "price_wan",
    "meets_constraints",
    "why_fit",
    "risks",
    "evidence_ids",
}
RECOMMENDATION_FIELDS = {"model", "trim", "year", "reason", "tradeoffs"}


def parse_decision_output(content: str) -> Tuple[Optional[Mapping[str, Any]], List[ValidationIssue]]:
    text = content.strip()
    if not text:
        return None, [ValidationIssue("$", "assistant content is empty")]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [
            ValidationIssue(
                "$",
                "invalid JSON at line {} column {}: {}".format(
                    exc.lineno, exc.colno, exc.msg
                ),
            )
        ]
    issues = validate_decision_output(parsed)
    return (parsed if isinstance(parsed, Mapping) else None), issues


def validate_decision_output(value: Any) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not isinstance(value, Mapping):
        return [ValidationIssue("$", "expected a JSON object")]

    _check_fields(value, TOP_LEVEL_FIELDS, "$", issues)
    _nonempty_string(value, "turn_summary", "$", issues)
    _string_array(value, "assumptions", "$", issues)

    if value.get("confidence") not in {"high", "medium", "low"}:
        issues.append(ValidationIssue("$.confidence", "must be high, medium, or low"))
    if value.get("status") not in {"candidate_only", "final"}:
        issues.append(
            ValidationIssue("$.status", "must be candidate_only or final")
        )

    constraints = value.get("effective_constraints")
    if not isinstance(constraints, list):
        issues.append(ValidationIssue("$.effective_constraints", "must be an array"))
    else:
        for index, item in enumerate(constraints):
            _validate_constraint(item, "$.effective_constraints[{}]".format(index), issues)

    candidates = value.get("candidate_cars")
    if not isinstance(candidates, list):
        issues.append(ValidationIssue("$.candidate_cars", "must be an array"))
    elif not 1 <= len(candidates) <= 5:
        issues.append(
            ValidationIssue("$.candidate_cars", "must contain between 1 and 5 cars")
        )
    else:
        for index, item in enumerate(candidates):
            _validate_candidate(item, "$.candidate_cars[{}]".format(index), issues)

    recommendation = value.get("final_recommendation")
    if recommendation is not None:
        _validate_recommendation(recommendation, "$.final_recommendation", issues)

    question = value.get("next_question")
    if question is not None and (not isinstance(question, str) or not question.strip()):
        issues.append(
            ValidationIssue("$.next_question", "must be null or a non-empty string")
        )

    if recommendation is not None and question is not None:
        issues.append(
            ValidationIssue(
                "$",
                "a final recommendation requires next_question to be null",
            )
        )
    if recommendation is None and question is None:
        issues.append(
            ValidationIssue(
                "$",
                "either final_recommendation or next_question must be present",
            )
        )
    if value.get("status") == "final" and recommendation is None:
        issues.append(
            ValidationIssue("$.status", "final status requires a recommendation")
        )

    return issues


def _check_fields(
    value: Mapping[str, Any],
    expected: set,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    for name in missing:
        issues.append(ValidationIssue("{}.{}".format(path, name), "is required"))
    for name in extra:
        issues.append(ValidationIssue("{}.{}".format(path, name), "is not allowed"))


def _nonempty_string(
    value: Mapping[str, Any],
    field: str,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        issues.append(
            ValidationIssue("{}.{}".format(path, field), "must be a non-empty string")
        )


def _string_array(
    value: Mapping[str, Any],
    field: str,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    item = value.get(field)
    if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
        issues.append(
            ValidationIssue("{}.{}".format(path, field), "must be an array of strings")
        )


def _validate_constraint(
    item: Any,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    if not isinstance(item, Mapping):
        issues.append(ValidationIssue(path, "must be an object"))
        return
    _check_fields(item, CONSTRAINT_FIELDS, path, issues)
    _nonempty_string(item, "name", path, issues)
    _nonempty_string(item, "value", path, issues)
    source_turn = item.get("source_turn")
    if isinstance(source_turn, bool) or not isinstance(source_turn, int) or source_turn < 1:
        issues.append(ValidationIssue(path + ".source_turn", "must be an integer >= 1"))
    if item.get("status") not in {"active", "superseded"}:
        issues.append(ValidationIssue(path + ".status", "must be active or superseded"))


def _validate_candidate(
    item: Any,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    if not isinstance(item, Mapping):
        issues.append(ValidationIssue(path, "must be an object"))
        return
    _check_fields(item, CANDIDATE_FIELDS, path, issues)
    for field in ("model", "trim", "why_fit"):
        _nonempty_string(item, field, path, issues)
    year = item.get("year")
    if isinstance(year, bool) or not isinstance(year, int):
        issues.append(ValidationIssue(path + ".year", "must be an integer"))
    price = item.get("price_wan")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0:
        issues.append(ValidationIssue(path + ".price_wan", "must be a non-negative number"))
    _string_array(item, "meets_constraints", path, issues)
    _string_array(item, "risks", path, issues)
    _string_array(item, "evidence_ids", path, issues)
    evidence = item.get("evidence_ids")
    if isinstance(evidence, list) and not evidence:
        issues.append(ValidationIssue(path + ".evidence_ids", "must not be empty"))


def _validate_recommendation(
    item: Any,
    path: str,
    issues: List[ValidationIssue],
) -> None:
    if not isinstance(item, Mapping):
        issues.append(ValidationIssue(path, "must be an object or null"))
        return
    _check_fields(item, RECOMMENDATION_FIELDS, path, issues)
    for field in ("model", "trim", "reason"):
        _nonempty_string(item, field, path, issues)
    year = item.get("year")
    if isinstance(year, bool) or not isinstance(year, int):
        issues.append(ValidationIssue(path + ".year", "must be an integer"))
    _string_array(item, "tradeoffs", path, issues)

