"""Score four-turn run records with the frozen semi-automatic rubric.

The rubric text lives in ``docs/evaluation-protocol-v1.md``; this module is its
executable form and must be frozen in the same commit.  It reads local run
records only, never calls a model API, and writes score tables plus a review
queue for the checks that cannot be decided mechanically.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from llm_eval.config import project_root


RUBRIC: Dict[str, Dict[str, Any]] = {
    "constraint_fit": {"label": "约束符合度", "max": 40, "turns": {1: 10, 2: 10, 4: 20}},
    "consistency": {"label": "多轮一致性", "max": 25, "turns": {2: 10, 3: 5, 4: 10}},
    "instruction": {"label": "指令遵循", "max": 15, "turns": {1: 3, 2: 3, 3: 5, 4: 4}},
    "truthfulness": {"label": "信息真实性", "max": 20, "turns": {1: 5, 2: 5, 3: 5, 4: 5}},
}

DIMENSIONS = ("constraint_fit", "consistency", "instruction", "truthfulness")
TURN_ORDER = (1, 2, 3, 4)
# Checks whose automated verdict may be overridden by a recorded manual review (D2).
REVIEWABLE_CHECKS = ("more_than_one_question",)
PRICE_TOLERANCE = Decimal("0.01")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

SEAT_HINTS = ("座位", "座", "座椅")
ADAS_HINTS = ("辅助驾驶", "智驾", "adas")
ENERGY_HINTS = (
    ("插电混动", ("插电混动", "插混", "phev")),
    ("纯电", ("纯电", "bev")),
    ("燃油", ("燃油", "汽油")),
)
BUDGET_HINTS = ("预算", "车价", "价格", "万元", "裸车")


def squeeze(value: Any) -> str:
    """Normalize free text for identity comparison (spacing and case ignored)."""
    if not isinstance(value, str):
        return ""
    return "".join(value.split()).casefold()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dedupe(values: Sequence[str]) -> List[str]:
    seen: List[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


class Catalog:
    """Frozen vehicle data keyed by source id."""

    def __init__(self, vehicles: Sequence[Mapping[str, Any]]):
        self.by_source: Dict[str, Mapping[str, Any]] = {}
        for vehicle in vehicles:
            source_id = str(as_dict(vehicle).get("source_id") or "").strip().upper()
            if source_id:
                self.by_source[source_id] = vehicle

    @staticmethod
    def identity(value: Mapping[str, Any]) -> Tuple[str, str, Any]:
        return (
            squeeze(value.get("model")),
            squeeze(value.get("trim")),
            value.get("year"),
        )


def match_vehicle(
    value: Any,
    catalog: Catalog,
    require_evidence: bool = True,
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Match one candidate to the frozen catalog.

    A candidate is only trusted through its ``evidence_ids``; matching on the
    typed identity fields alone is reported as ``identity_fields`` so that the
    truthfulness item can reject it.
    """
    payload = as_dict(value)
    if not payload:
        return None, None, ["not_an_object"]
    identity = Catalog.identity(payload)
    evidence_ids = as_list(payload.get("evidence_ids"))
    problems: List[str] = []
    matched: Optional[str] = None
    for raw in evidence_ids:
        source_id = str(raw).strip().upper()
        source = catalog.by_source.get(source_id)
        if source is None:
            problems.append("unknown_evidence_id:{}".format(raw))
            continue
        if Catalog.identity(source) != identity:
            problems.append("evidence_id_conflict:{}".format(raw))
            continue
        matched = source_id
    if matched:
        distinct = {str(raw).strip().upper() for raw in evidence_ids}
        if len(distinct) > 1:
            problems.append("multiple_evidence_ids")
        return matched, "evidence_id", dedupe(problems)
    for source_id, source in catalog.by_source.items():
        if Catalog.identity(source) == identity:
            if require_evidence:
                problems.append("missing_matching_evidence_id")
            return source_id, "identity_fields", dedupe(problems)
    problems.append("unknown_vehicle")
    return None, None, dedupe(problems)


def check_vehicle_facts(payload: Mapping[str, Any], source: Mapping[str, Any]) -> List[str]:
    """Verify the facts a candidate payload actually states."""
    problems: List[str] = []
    price = payload.get("price_wan")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        problems.append("price_missing")
    elif abs(Decimal(str(price)) - Decimal(str(source.get("price_wan")))) > PRICE_TOLERANCE:
        problems.append("price_mismatch:{}!={}".format(price, source.get("price_wan")))
    if payload.get("year") != source.get("year"):
        problems.append("year_mismatch")
    return problems


def check_comparison_row(row: Mapping[str, Any], source: Mapping[str, Any]) -> List[str]:
    """Verify the joined parameter table against the frozen facts."""
    problems: List[str] = []
    for field in ("price_wan", "energy", "seats", "adas", "model", "trim", "year"):
        if field not in row:
            continue
        if row.get(field) is None:
            problems.append("comparison_{}_missing".format(field))
        elif field == "price_wan":
            if abs(Decimal(str(row[field])) - Decimal(str(source.get(field)))) > PRICE_TOLERANCE:
                problems.append("comparison_price_mismatch")
        elif row.get(field) != source.get(field):
            problems.append("comparison_{}_mismatch".format(field))
    for field in ("price_wan", "energy", "seats", "adas"):
        if row.get(field) is None:
            problems.append("comparison_{}_missing".format(field))
    return dedupe(problems)


def evaluate_candidates(payload: Optional[Mapping[str, Any]], catalog: Catalog) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for candidate in as_list(as_dict(payload).get("candidate_cars")):
        source_id, mode, problems = match_vehicle(candidate, catalog)
        if source_id:
            problems = dedupe(problems + check_vehicle_facts(as_dict(candidate), catalog.by_source[source_id]))
        results.append({
            "candidate": as_dict(candidate),
            "source_id": source_id,
            "match": mode,
            "problems": dedupe(problems),
        })
    return results


def parse_number(text: str) -> Optional[Decimal]:
    numbers = NUMBER_RE.findall(text)
    if not numbers:
        return None
    return Decimal(numbers[0])


def parse_budget(text: str) -> Optional[Decimal]:
    amount = parse_number(text)
    if amount is None:
        return None
    if "万" not in text and amount >= Decimal(1000):
        amount = amount / Decimal(10000)
    return amount


def parse_energy(text: str) -> List[str]:
    lowered = text.casefold()
    return [name for name, hints in ENERGY_HINTS if any(hint in lowered for hint in hints)]


def classify_constraint(entry: Mapping[str, Any]) -> Tuple[Optional[str], Any]:
    """Map one declared constraint to a scored field and value.

    Only the fields the frozen data can check are extracted; free text without a
    recognisable field stays unscored instead of being guessed.
    """
    name = str(entry.get("name") or "")
    value = str(entry.get("value") or "")
    text = "{} {}".format(name, value)
    lowered = text.casefold()
    if any(hint in text for hint in SEAT_HINTS) and not any(hint in text for hint in ("预算", "车价")):
        seats = parse_number(value)
        return "seats", int(seats) if seats is not None else None
    if any(hint in lowered for hint in ADAS_HINTS) or "l2" in lowered or "l1" in lowered:
        if "l2" in lowered:
            return "adas", "L2"
        if "l1" in lowered:
            return "adas", "L1"
        return "adas", None
    energies = parse_energy(text)
    if energies:
        return "energy", energies[0] if len(energies) == 1 else tuple(sorted(energies))
    if any(hint in text for hint in BUDGET_HINTS):
        return "price_wan", parse_budget(value)
    return None, None


def classify_constraints(payload: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for item in as_list(as_dict(payload).get("effective_constraints")):
        entry = as_dict(item)
        field, value = classify_constraint(entry)
        entries.append({
            "field": field,
            "value": value,
            "status": entry.get("status") if entry.get("status") in ("active", "superseded") else "unknown",
            "source_turn": entry.get("source_turn") if isinstance(entry.get("source_turn"), int) else None,
            "raw": "{}={}".format(entry.get("name"), entry.get("value")),
        })
    return entries


def meets(constraint: Mapping[str, Any], entry: Mapping[str, Any]) -> bool:
    got = entry.get("value")
    if got is None:
        return False
    field = constraint.get("field")
    want = constraint.get("value")
    if field == "price_wan":
        return isinstance(got, Decimal) and got <= Decimal(str(want))
    if field == "seats":
        return isinstance(got, int) and got >= want
    return got == want


def same_value(left: Any, right: Any) -> bool:
    if isinstance(left, Decimal) and isinstance(right, (int, float, Decimal)):
        return left == Decimal(str(right))
    return left == right


def count_questions(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    return value.count("？") + value.count("?")


def describes_comparison_fields(candidate: Mapping[str, Any]) -> List[str]:
    """Fallback check for turn 3 when no joined parameter table is recorded."""
    payload = as_dict(candidate.get("candidate"))
    text = str(payload.get("why_fit") or "")
    found = {
        "price": bool(NUMBER_RE.findall(text)),
        "energy": bool(parse_energy(text)),
        "seats": any(hint in text for hint in ("座", "座位")),
        "adas": any(hint in text.casefold() for hint in ADAS_HINTS) or "l2" in text.casefold() or "l1" in text.casefold(),
    }
    return [name for name, ok in found.items() if not ok]


def analyze_turn(record_turn: Optional[Mapping[str, Any]], catalog: Catalog) -> Dict[str, Any]:
    entry = as_dict(record_turn)
    payload = entry.get("parsed_output")
    payload = payload if isinstance(payload, dict) else None
    valid = bool(payload is not None and entry.get("valid") is True)
    candidates = evaluate_candidates(payload, catalog)
    final = None
    if payload is not None:
        final_payload = payload.get("final_recommendation")
        if isinstance(final_payload, dict):
            source_id, mode, problems = match_vehicle(final_payload, catalog, require_evidence=False)
            final = {"source_id": source_id, "match": mode, "problems": problems, "payload": final_payload}
    return {
        "record": entry,
        "payload": payload,
        "valid": valid,
        "candidates": candidates,
        "final": final,
        "audit": entry.get("comparison_audit") if isinstance(entry.get("comparison_audit"), dict) else None,
        "comparison_rows": payload.get("parameter_comparison") if payload is not None
        and isinstance(payload.get("parameter_comparison"), list) else None,
    }


def consistency_problems(
    turn_no: int,
    payload: Optional[Mapping[str, Any]],
    reference_turn: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    eligible: Sequence[str],
) -> Tuple[List[str], List[str]]:
    """Check the declared constraint ledger for retention, update and replacement."""
    problems: List[str] = []
    hints: List[str] = []
    entries = classify_constraints(payload)
    active = [entry for entry in entries if entry["status"] == "active"]
    for constraint in reference_turn["constraints"]:
        if constraint["status"] != "active":
            continue
        if any(entry["field"] == constraint["field"] and meets(constraint, entry) for entry in active):
            continue
        prefix = "new_constraint_missing" if constraint["source_turn"] == turn_no else "retained_constraint_missing"
        problems.append("{}:{}".format(prefix, constraint["field"]))
    for constraint in reference_turn["constraints"]:
        if constraint["status"] != "superseded":
            continue
        stale = [
            entry for entry in active
            if entry["field"] == constraint["field"] and same_value(entry["value"], constraint["value"])
        ]
        if stale:
            problems.append("superseded_value_still_active:{}".format(constraint["field"]))
        elif not any(
            entry["field"] == constraint["field"] and entry["status"] == "superseded"
            for entry in entries
        ):
            hints.append("superseded_value_not_declared:{}".format(constraint["field"]))
    if turn_no == 3:
        outside = [candidate["source_id"] for candidate in candidates if candidate["source_id"] not in eligible]
        if outside:
            problems.append("candidate_outside_active_constraints")
    return problems, hints


def instruction_problems(
    turn_no: int,
    analysis: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> List[str]:
    payload = as_dict(analysis.get("payload"))
    problems: List[str] = []
    if turn_no < 4 and count_questions(payload.get("next_question")) > 1:
        problems.append("more_than_one_question")
    audit = analysis.get("audit")
    if turn_no != 3 and audit is not None and audit.get("passed") is not True:
        problems.append("comparison_rows_outside_turn3")
    if turn_no in (1, 2):
        if not as_list(payload.get("candidate_cars")):
            problems.append("candidate_list_missing")
    elif turn_no == 3:
        rows = analysis.get("comparison_rows")
        if rows is not None:
            row_sources = {str(as_dict(row).get("source_id") or "").strip().upper() for row in rows}
            missing = [
                candidate["source_id"] for candidate in candidates
                if candidate["source_id"] and candidate["source_id"] not in row_sources
            ]
            if missing or not rows:
                problems.append("parameter_table_incomplete")
        else:
            comparison = as_dict(analysis["record"]).get("parameter_comparison")
            if isinstance(comparison, dict):
                legacy_rows = as_list(comparison.get("rows"))
                row_sources = {
                    str(as_dict(row).get("source_id") or "").strip().upper() for row in legacy_rows
                }
                unmatched = as_list(comparison.get("unmatched_candidates"))
                missing = [
                    candidate["source_id"] for candidate in candidates
                    if candidate["source_id"] and candidate["source_id"] not in row_sources
                ]
                if unmatched or missing or not legacy_rows:
                    problems.append("parameter_table_incomplete")
            elif int(as_dict(audit).get("checked_rows") or 0) > 0:
                pass
            else:
                incomplete = [candidate for candidate in candidates if describes_comparison_fields(candidate)]
                if incomplete or not candidates:
                    problems.append("parameter_table_text_missing")
    elif turn_no == 4:
        final = analysis.get("final")
        if final is None:
            problems.append("final_recommendation_missing")
        else:
            if not str(as_dict(final.get("payload")).get("reason") or "").strip():
                problems.append("final_reason_missing")
            if not as_list(as_dict(final.get("payload")).get("tradeoffs")):
                problems.append("final_tradeoffs_missing")
    return problems


def truthfulness_problems(
    turn_no: int,
    analysis: Mapping[str, Any],
    catalog: Catalog,
) -> Optional[List[str]]:
    """Return None when the turn cannot be verified without manual review."""
    problems: List[str] = []
    for candidate in analysis["candidates"]:
        if candidate["match"] != "evidence_id":
            problems.append("candidate_not_linked_by_evidence_id")
        problems.extend(candidate["problems"])
    if turn_no == 4:
        final = analysis.get("final")
        if final is None:
            problems.append("final_recommendation_missing")
        elif final["source_id"] is None:
            problems.append("final_unknown_vehicle")
        else:
            problems.extend(final["problems"])
    if turn_no == 3:
        rows = analysis.get("comparison_rows")
        audit = analysis.get("audit")
        if audit is not None:
            if audit.get("passed") is not True:
                problems.append("comparison_audit_failed")
                problems.extend(str(issue) for issue in as_list(audit.get("issues")))
        elif rows is not None:
            if not rows:
                problems.append("comparison_rows_missing")
            for row in rows:
                row = as_dict(row)
                source = catalog.by_source.get(str(row.get("source_id") or "").strip().upper())
                if source is None:
                    problems.append("comparison_unknown_source_id")
                    continue
                problems.extend(check_comparison_row(row, source))
        else:
            comparison = as_dict(analysis["record"]).get("parameter_comparison")
            if not isinstance(comparison, dict):
                return None
            if as_list(comparison.get("unmatched_candidates")):
                problems.append("comparison_unmatched_candidates")
            legacy_rows = as_list(comparison.get("rows"))
            if not legacy_rows:
                problems.append("comparison_rows_missing")
            for row in legacy_rows:
                row = as_dict(row)
                source = catalog.by_source.get(str(row.get("source_id") or "").strip().upper())
                if source is None:
                    problems.append("comparison_unknown_source_id")
                    continue
                problems.extend(check_comparison_row(row, source))
    return dedupe(problems)


def make_item(dimension: str, turn_no: int, max_points: int, reason: str = "", auto: bool = True) -> Dict[str, Any]:
    passed = not reason
    return {
        "turn": turn_no,
        "dimension": dimension,
        "max": max_points,
        "points": max_points if (passed and auto) else 0,
        "passed": bool(passed),
        "auto": auto,
        "reason": reason,
    }


def is_reviewable(reason: str) -> bool:
    """A failed item may be reopened by a reviewer only when every reason is listed.

    Partial overrides would silently waive other failed checks, so an item that
    also fails a non-reviewable check stays closed.
    """
    parts = [part for part in reason.split(";") if part]
    return bool(parts) and all(part in REVIEWABLE_CHECKS for part in parts)


def final_source_id_of(analysis: Mapping[str, Any]) -> str:
    final = analysis.get(4, {}).get("final")
    if not final:
        return ""
    return str(final.get("source_id") or "未定位")


def model_key_of(record: Mapping[str, Any]) -> str:
    if record.get("model_key"):
        return str(record["model_key"])
    for turn in as_list(record.get("turns")):
        value = as_dict(turn).get("model_key")
        if value:
            return str(value)
    run_id = str(record.get("run_id") or "")
    return run_id.split("-")[0] if run_id else "unknown"


def turn_metrics(record: Mapping[str, Any]) -> Dict[str, Any]:
    total = 0
    missing = False
    latency = 0
    for turn in as_list(record.get("turns")):
        entry = as_dict(turn)
        usage = as_dict(entry.get("total_usage"))
        value = usage.get("total_tokens")
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
        else:
            missing = True
        turn_latency = entry.get("total_latency_ms")
        if isinstance(turn_latency, int):
            latency += turn_latency
    return {
        "tokens": None if missing else total,
        "tokens_missing": missing,
        "elapsed_ms": record.get("elapsed_ms"),
        "turn_latency_ms": latency,
    }


def score_run(
    record: Mapping[str, Any],
    references: Mapping[str, Mapping[str, Any]],
    catalog: Catalog,
    review: Optional[Mapping[Tuple[str, int, str], str]] = None,
) -> Dict[str, Any]:
    run_id = str(record.get("run_id") or "")
    scenario_id = str(record.get("scenario_id") or "")
    reference = references.get(scenario_id)
    if reference is None:
        raise ValueError("{}: unknown scenario {!r}".format(run_id or "<no run_id>", scenario_id))

    turns: Dict[int, Mapping[str, Any]] = {}
    for entry in as_list(record.get("turns")):
        if isinstance(entry, dict) and isinstance(entry.get("turn"), int):
            turns[entry["turn"]] = entry
    analysis = {turn_no: analyze_turn(turns.get(turn_no), catalog) for turn_no in TURN_ORDER}

    items: List[Dict[str, Any]] = []
    hints: List[Dict[str, Any]] = []

    for dimension in DIMENSIONS:
        for turn_no in sorted(RUBRIC[dimension]["turns"]):
            max_points = RUBRIC[dimension]["turns"][turn_no]
            entry = analysis[turn_no]
            reference_turn = reference["turns"][turn_no - 1]
            eligible = reference_turn["eligible_source_ids"]
            if not entry["valid"]:
                items.append(make_item(dimension, turn_no, max_points, "turn_missing_or_invalid"))
                continue
            if dimension == "constraint_fit":
                reason = ""
                if turn_no == 4:
                    final = entry["final"]
                    if final is None:
                        reason = "final_recommendation_missing"
                    elif final["source_id"] not in eligible:
                        reason = "final_outside_eligible_set"
                else:
                    source_ids = [candidate["source_id"] for candidate in entry["candidates"]]
                    if not source_ids:
                        reason = "candidates_empty"
                    elif any(source_id not in eligible for source_id in source_ids):
                        reason = "candidate_outside_eligible_set"
                items.append(make_item(dimension, turn_no, max_points, reason))
            elif dimension == "consistency":
                problems, ledger_hints = consistency_problems(
                    turn_no, entry["payload"], reference_turn, entry["candidates"], eligible
                )
                for hint in ledger_hints:
                    hints.append({"turn": turn_no, "dimension": dimension, "hint": hint})
                items.append(make_item(dimension, turn_no, max_points, ";".join(problems)))
            elif dimension == "instruction":
                items.append(make_item(
                    dimension, turn_no, max_points,
                    ";".join(instruction_problems(turn_no, entry, entry["candidates"])),
                ))
            else:
                problems = truthfulness_problems(turn_no, entry, catalog)
                if problems is None:
                    items.append(make_item(
                        dimension, turn_no, max_points,
                        "parameter_table_absent_manual_verification_required", auto=False,
                    ))
                else:
                    items.append(make_item(dimension, turn_no, max_points, ";".join(problems)))

    for item in items:
        item["reviewable"] = is_reviewable(item["reason"])

    if review:
        for item in items:
            verdict = review.get((run_id, item["turn"], item["dimension"]))
            if verdict not in ("pass", "fail"):
                continue
            item["reviewed"] = True
            if verdict == "pass":
                item.update(points=item["max"], passed=True, reason=(item["reason"] + ";manual_pass").lstrip(";"))
            else:
                item.update(points=0, passed=False, reason=(item["reason"] + ";manual_fail").lstrip(";"))

    score = sum(item["points"] for item in items)
    pending = sum(item["max"] for item in items if not item["auto"] and not item.get("reviewed"))
    subtotals = {
        dimension: sum(item["points"] for item in items if item["dimension"] == dimension)
        for dimension in DIMENSIONS
    }

    success: Optional[bool]
    if pending:
        success = None
    elif any(not analysis[turn_no]["valid"] for turn_no in TURN_ORDER):
        success = False
    else:
        final = analysis[4]["final"]
        final_ok = bool(final and final["source_id"] in reference["turns"][3]["eligible_source_ids"])
        success = bool(final_ok and subtotals["truthfulness"] == RUBRIC["truthfulness"]["max"])

    review_rows = [
        {
            "run_id": run_id,
            "model_key": model_key_of(record),
            "scenario_id": scenario_id,
            "repetition": record.get("repetition"),
            "turn": item["turn"],
            "dimension": item["dimension"],
            "check": item["reason"],
            "kind": "blocking" if not item["auto"] else "override",
            "default": "pending" if not item["auto"] else "fail",
            "max_points": item["max"],
            "verdict": "",
        }
        for item in items
        if not item["auto"] or item.get("reviewable")
    ]

    return {
        "run_id": run_id,
        "model_key": model_key_of(record),
        "scenario_id": scenario_id,
        "repetition": record.get("repetition"),
        "batch_kind": record.get("batch_kind"),
        "turns_present": sorted(turns),
        "final_source_id": final_source_id_of(analysis),
        "items": items,
        "subtotals": subtotals,
        "score": score,
        "pending_points": pending,
        "success": success,
        "metrics": turn_metrics(record),
        "review_rows": review_rows,
        "hints": hints,
    }


def read_review(path: Optional[Path]) -> Dict[Tuple[str, int, str], str]:
    verdicts: Dict[Tuple[str, int, str], str] = {}
    if not path or not path.exists():
        return verdicts
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            verdict = str(row.get("verdict") or "").strip().lower()
            if verdict not in ("pass", "fail"):
                continue
            try:
                turn = int(row.get("turn"))
            except (TypeError, ValueError):
                continue
            verdicts[(str(row.get("run_id") or "").strip(), turn, str(row.get("dimension") or "").strip())] = verdict
    return verdicts


def load_records(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for file in sorted(path.glob("*.json")):
        try:
            value = json.loads(file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get("turns"), list):
            records.append(value)
    if not records:
        raise SystemExit("No run records found in {}".format(path))
    return records


def aggregate(results: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for result in results:
        groups.setdefault((result["model_key"], result["scenario_id"]), []).append(result)
        groups.setdefault((result["model_key"], "全部场景"), []).append(result)
    rows: List[Dict[str, Any]] = []
    for (model_key, scenario_id), items in sorted(groups.items()):
        scores = [item["score"] for item in items]
        token_values = [item["metrics"]["tokens"] for item in items if item["metrics"]["tokens"] is not None]
        elapsed_values = [item["metrics"]["elapsed_ms"] for item in items if isinstance(item["metrics"]["elapsed_ms"], int)]
        # D7: report which eligible vehicle was chosen, never treat switching as instability.
        mix: Dict[str, int] = {}
        for item in items:
            key = item.get("final_source_id") or "未给出"
            mix[key] = mix.get(key, 0) + 1
        mix_text = ";".join(
            "{}×{}".format(name, count) for name, count in sorted(mix.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        rows.append({
            "model_key": model_key,
            "scenario_id": scenario_id,
            "runs": len(items),
            "success": sum(1 for item in items if item["success"] is True),
            "failed": sum(1 for item in items if item["success"] is False),
            "undecided": sum(1 for item in items if item["success"] is None),
            "mean_score": round(statistics.fmean(scores), 2),
            "min_score": min(scores),
            "max_score": max(scores),
            "stdev_score": round(statistics.stdev(scores), 2) if len(scores) > 1 else "",
            "pending_points": sum(item["pending_points"] for item in items),
            "mean_tokens": round(statistics.fmean(token_values)) if token_values else "",
            "mean_elapsed_s": round(statistics.fmean(elapsed_values) / 1000, 1) if elapsed_values else "",
            "distinct_recommendations": len(mix),
            "recommendation_mix": mix_text,
        })
    return rows


SCORE_FIELDS = (
    "run_id", "model_key", "scenario_id", "repetition", "batch_kind",
    "constraint_fit", "consistency", "instruction", "truthfulness",
    "score", "pending_points", "success", "final_source_id", "tokens", "elapsed_ms", "failed_checks",
)
SUMMARY_FIELDS = (
    "model_key", "scenario_id", "runs", "success", "failed", "undecided",
    "mean_score", "min_score", "max_score", "stdev_score",
    "pending_points", "mean_tokens", "mean_elapsed_s",
    "distinct_recommendations", "recommendation_mix",
)
REVIEW_FIELDS = (
    "run_id", "model_key", "scenario_id", "repetition",
    "turn", "dimension", "check", "kind", "default", "max_points", "verdict",
)
HINT_FIELDS = ("run_id", "turn", "dimension", "hint")

# Column layout expected by ``python -m llm_eval.report --scores`` so the same
# scorecard can feed the results charts without a second transcription step.
REPORT_SCORE_FIELDS = (
    "run_id", "constraint_adherence_40", "multi_turn_consistency_25",
    "instruction_following_15", "factuality_20", "reviewer", "notes",
)
REPORT_SCORE_MAP = {
    "constraint_adherence_40": "constraint_fit",
    "multi_turn_consistency_25": "consistency",
    "instruction_following_15": "instruction",
    "factuality_20": "truthfulness",
}


def report_score_rows(results: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Rows for ``llm_eval.report --scores``.

    Runs with unresolved manual checks leave the four columns blank on purpose:
    the report then counts them as unscored instead of charting a half-verified
    total.
    """
    rows: List[Dict[str, Any]] = []
    for result in results:
        if result["pending_points"]:
            rows.append({
                "run_id": result["run_id"],
                "reviewer": "",
                "notes": "待人工复核 {} 分，暂不输出分数".format(result["pending_points"]),
            })
            continue
        failed = [
            "{}#{}:{}".format(item["dimension"], item["turn"], item["reason"])
            for item in result["items"] if not item["passed"]
        ]
        row: Dict[str, Any] = {
            "run_id": result["run_id"],
            "reviewer": "llm_eval.scoring（自动）",
            "notes": "自动评分；全部通过" if not failed else "自动评分；未通过：" + " | ".join(failed),
        }
        for alias, dimension in REPORT_SCORE_MAP.items():
            row[alias] = result["subtotals"][dimension]
        rows.append(row)
    return rows


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_summary_markdown(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    runs: int,
    pending: int,
    overrides: int = 0,
) -> None:
    lines = [
        "# 评分汇总",
        "",
        "评分规则见 `docs/evaluation-protocol-v1.md`，由 `src/llm_eval/scoring.py` 执行。",
        "共 {} 次运行，其中待人工判定分值 {} 分，另有 {} 项可人工改判。".format(runs, pending, overrides),
        "",
        "| 模型 | 场景 | 次数 | 成功 | 失败 | 未定 | 均分 | 区间 | 标准差 | 待复核 | 推荐分布 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {model_key} | {scenario_id} | {runs} | {success} | {failed} | {undecided} | "
            "{mean_score} | {min_score}–{max_score} | {stdev_score} | {pending_points} | "
            "{recommendation_mix} |".format(**row)
        )
    lines.extend([
        "",
        "成功定义：四轮均通过结构校验、最终推荐落在当轮参考集合内、信息真实性得满分。",
        "待复核项确认前不计入成功数；样本量小，结论只适用于本次数据、场景与运行设置。",
        "推荐分布是描述性统计：多款合格车型之间切换不扣分，也不据此判为不稳定。",
        "完整分数见 `scores.csv`，待判项见 `review-queue.csv`。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def score_rows(results: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for result in results:
        metrics = result["metrics"]
        failed = [
            "{}#{}:{}".format(item["dimension"], item["turn"], item["reason"])
            for item in result["items"] if not item["passed"]
        ]
        rows.append({
            "run_id": result["run_id"],
            "model_key": result["model_key"],
            "scenario_id": result["scenario_id"],
            "repetition": result["repetition"],
            "batch_kind": result["batch_kind"],
            "constraint_fit": result["subtotals"]["constraint_fit"],
            "consistency": result["subtotals"]["consistency"],
            "instruction": result["subtotals"]["instruction"],
            "truthfulness": result["subtotals"]["truthfulness"],
            "score": result["score"],
            "pending_points": result["pending_points"],
            "success": "" if result["success"] is None else str(result["success"]).lower(),
            "final_source_id": result.get("final_source_id", ""),
            "tokens": "" if metrics["tokens"] is None else metrics["tokens"],
            "elapsed_ms": "" if metrics["elapsed_ms"] is None else metrics["elapsed_ms"],
            "failed_checks": " | ".join(failed),
        })
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", required=True, type=Path, help="批次目录，由 llm_eval.evaluate 写入")
    parser.add_argument("--out", type=Path, help="输出目录，默认 <runs>/scores")
    parser.add_argument("--config", type=Path, help="默认 configs/evaluation-v1.json")
    parser.add_argument("--reference", type=Path, help="默认 data/reference-answers-v1.json")
    parser.add_argument("--review", type=Path, help="回填 verdict 后的复核表")
    args = parser.parse_args(argv)

    root = project_root()
    config_path = args.config or root / "configs" / "evaluation-v1.json"
    reference_path = args.reference or root / "data" / "reference-answers-v1.json"
    design = json.loads(config_path.read_text(encoding="utf-8-sig"))
    reference_payload = json.loads(reference_path.read_text(encoding="utf-8-sig"))
    references = {scenario["scenario_id"]: scenario for scenario in reference_payload["scenarios"]}
    catalog = Catalog(design["vehicle_data"])
    review = read_review(args.review)
    out = args.out or args.runs / "scores"

    results = [score_run(record, references, catalog, review) for record in load_records(args.runs)]
    summary = aggregate(results)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "scores.csv", score_rows(results), SCORE_FIELDS)
    write_csv(out / "summary.csv", summary, SUMMARY_FIELDS)
    write_csv(out / "review-queue.csv", [row for result in results for row in result["review_rows"]], REVIEW_FIELDS)
    write_csv(out / "report-scores.csv", report_score_rows(results), REPORT_SCORE_FIELDS)
    write_csv(
        out / "review-hints.csv",
        [{"run_id": result["run_id"], **hint} for result in results for hint in result["hints"]],
        HINT_FIELDS,
    )
    pending = sum(result["pending_points"] for result in results)
    overrides = sum(
        1 for result in results for row in result["review_rows"] if row["kind"] == "override"
    )
    write_summary_markdown(out / "summary.md", summary, len(results), pending, overrides)
    (out / "scores.json").write_text(
        json.dumps({"rubric": RUBRIC, "runs": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("scored {} runs, pending manual review {} points".format(len(results), pending))
    for row in summary:
        print("  {} / {}: n={} success={} failed={} undecided={} mean={} range={}-{}".format(
            row["model_key"], row["scenario_id"], row["runs"], row["success"],
            row["failed"], row["undecided"], row["mean_score"], row["min_score"], row["max_score"],
        ))
    print("outputs: {}".format(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
