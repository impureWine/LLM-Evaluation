"""Validate the fixed teaching dataset and derive references without API calls."""

import argparse
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from llm_eval.config import project_root
from llm_eval.evaluate import scenario_messages
from llm_eval.prompts import PromptBundle


REFERENCE_PATH = "data/reference-answers-v1.json"
LOCK_PATH = "data/release-v1.json"
LOCKED_PATHS = (
    "configs/evaluation-v1.json", "configs/scenario-rules-v1.json",
    "data/vehicle-sources-v1.json", REFERENCE_PATH,
    "configs/models.json", "prompts/system_v1.md", "prompts/initial_user_v1.md",
    "prompts/followup_user_v1.md", "prompts/output_schema_v1.json",
    "docs/evaluation-protocol-v1.md",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(root, path):
    return json.loads((root / path).read_text(encoding="utf-8-sig"))


def save_json(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text_hash(path):
    # Matches evaluate.py: UTF-8 text, BOM removed, CRLF normalized to LF.
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()


def check_constraint(item, turn):
    require(item["id"] and item["source_turn"] == turn, "Invalid constraint id/source_turn")
    field, op, value = item["field"], item["operator"], item["value"]
    allowed = {"price_wan": "lte", "seats": "gte", "energy": "eq", "adas": "eq"}
    require(field in allowed and op == allowed[field], "Unsupported constraint field/operator")
    if field in ("price_wan", "seats"):
        require(type(value) in (int, float) and Decimal(str(value)).is_finite()
                and value > 0, "Numeric constraints must be finite and positive")
        if field == "seats":
            require(type(value) is int, "Seat threshold must be an integer")
    else:
        values = ("纯电", "插电混动", "燃油") if field == "energy" else ("L1", "L2")
        require(value in values, "Unknown constraint enum value")


def constraint_history(rule, turn):
    require(type(turn) is int and 1 <= turn <= 4, "Turn must be 1..4")
    history = []
    for item in rule["initial_constraints"]:
        check_constraint(item, 1)
        require(not any(h["id"] == item["id"] or h["field"] == item["field"] for h in history),
                "Duplicate initial constraint")
        history.append(dict(item, status="active"))
    for event in rule["events"]:
        require(event["turn"] == 2, "This v1 protocol only changes constraints at turn 2")
        check_constraint(event["constraint"], event["turn"])
        require(event["action"] in ("add", "replace"), "Unknown update action")
        if event["turn"] > turn:
            continue
        item = event["constraint"]
        existing = [h for h in history if h["id"] == item["id"] and h["status"] == "active"]
        if event["action"] == "replace":
            require(len(existing) == 1 and existing[0]["field"] == item["field"],
                    "Replacement must target an active constraint on the same field")
            existing[0]["status"] = "superseded"
        else:
            require(not existing, "Add must not overwrite an active constraint")
        require(not any(h["field"] == item["field"] and h["status"] == "active" for h in history),
                "Duplicate active field")
        history.append(dict(item, status="active"))
    return history


def fits(vehicle, constraint):
    left, right = vehicle[constraint["field"]], constraint["value"]
    op = constraint["operator"]
    if op == "eq":
        return left == right
    if op == "lte":
        return Decimal(str(left)) <= Decimal(str(right))
    if op == "gte":
        return Decimal(str(left)) >= Decimal(str(right))
    raise ValueError("Unsupported constraint operator")


def derive_references(design, rules):
    scenarios = {s["id"]: s for s in design["scenarios"]}
    rule_ids = [s["id"] for s in rules["scenarios"]]
    require(len(scenarios) == len(design["scenarios"]) >= 3, "Expected unique scenario ids")
    require(len(rule_ids) == len(set(rule_ids)) and set(rule_ids) == set(scenarios),
            "Scenario rules must match runtime scenarios")
    require(rules["turns_per_task"] == 4, "Protocol requires four turns")
    references = []
    for rule in rules["scenarios"]:
        turns = []
        for turn in range(1, 5):
            history = constraint_history(rule, turn)
            active = [h for h in history if h["status"] == "active"]
            require(any(h["field"] == "price_wan" for h in active) and len(active) >= 2,
                    "Each turn needs a budget and a non-budget hard constraint")
            accepted, rejected = [], []
            for vehicle in design["vehicle_data"]:
                failures = [h["id"] for h in active if not fits(vehicle, h)]
                if failures:
                    rejected.append({"source_id": vehicle["source_id"], "failed_constraints": failures})
                else:
                    accepted.append(vehicle["source_id"])
            turns.append({"turn": turn, "constraints": history,
                          "eligible_source_ids": accepted, "excluded": rejected})
        scenario = scenarios[rule["id"]]
        for field, index in (("expected_initial", 0), ("expected_final", 3)):
            expected = scenario[field]
            require(len(expected) == len(set(expected)), "Duplicate expected source ids")
            require(set(expected) == set(turns[index]["eligible_source_ids"]),
                    "Reference mismatch: {} {}".format(rule["id"], field))
        require(all(t["eligible_source_ids"] for t in turns), "Base scenarios must have a solution")
        references.append({"scenario_id": rule["id"], "turns": turns})
    return {"version": "reference-answers-v1", "data_kind": "teaching_simulation",
            "visibility": "scoring_only", "tie_policy": "任一合格车型均可作为最终推荐；不强制唯一最优。",
            "scenarios": references}


def validate_inputs(root):
    design = read_json(root, "configs/evaluation-v1.json")
    rules = read_json(root, "configs/scenario-rules-v1.json")
    sources = read_json(root, "data/vehicle-sources-v1.json")
    require(sources["data_kind"] == "teaching_simulation", "Simulation label required")
    vehicles = design["vehicle_data"]
    ids = [v["source_id"] for v in vehicles]
    require(len(ids) == len(set(ids)) and ids, "Vehicle ids must be unique and nonempty")
    source_ids = [s["source_id"] for s in sources["sources"]]
    require(len(source_ids) == len(set(source_ids)) and set(source_ids) == set(ids),
            "Vehicle source coverage differs from manifest")
    for v in vehicles:
        require(all(k in v for k in sources["field_dictionary"]), "Missing vehicle field")
        require(type(v["year"]) is int and 1900 <= v["year"] <= 2100, "Invalid model year")
        require(type(v["seats"]) is int and v["seats"] > 0, "Invalid vehicle seats")
        require(type(v["price_wan"]) in (int, float) and Decimal(str(v["price_wan"])).is_finite()
                and v["price_wan"] > 0, "Invalid vehicle price")
        require(v["energy"] in sources["field_dictionary"]["energy"]["values"], "Invalid energy")
        require(v["adas"] in sources["field_dictionary"]["adas"]["values"], "Invalid ADAS label")
        source = next(s for s in sources["sources"] if s["source_id"] == v["source_id"])
        require(all(source[k] == v[k] for k in ("model", "trim", "year")), "Source identity mismatch")
        require(source["source_date"] and source["accessed_on"] and source["source_url"]
                and set(source["covers_fields"]) == set(v), "Incomplete provenance")
    bundle = PromptBundle.from_directory(root / "prompts")
    for scenario in design["scenarios"]:
        rule = next(r for r in rules["scenarios"] if r["id"] == scenario["id"])
        scripts = rule["turn_scripts"]
        require([s["turn"] for s in scripts] == [1, 2, 3, 4], "Invalid turn script sequence")
        require(scripts[0]["user_message"] == scenario["user_request"], "Initial script drift")
        initial, followups = scenario_messages(bundle, scenario, vehicles)
        expected_followups = [bundle.followup_message(s["turn"], s["user_message"], s["change_rule"])
                              for s in scripts[1:]]
        require(followups == expected_followups, "Follow-up script differs from runner")
        sentinel = copy.deepcopy(scenario)
        sentinel["expected_initial"] = sentinel["expected_final"] = ["REFERENCE_LEAK_SENTINEL"]
        require(scenario_messages(bundle, sentinel, vehicles) == (initial, followups),
                "Reference answers leaked into runtime messages")
    return derive_references(design, rules)


def make_lock(root):
    return {"version": "data-release-v1.1-candidate", "status": "prepared_for_team_freeze",
            "prepared_on": "2026-11-09", "maintainer": "庄剀涵（102400435）",
            "baseline_commit": "7d6e7c214459488d5310a2390cd9f0abbae3dd70",
            "hash_method": "sha256_utf8_text_bom_removed_newlines_lf",
            "note": "结构化参数对比契约为v1.1候选修订；材料已校验但仍待团队冻结审核，不能据此声明18次实验已完成。",
            "files": {p: text_hash(root / p) for p in LOCKED_PATHS}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--write-reference", action="store_true", help="Regenerate local scoring references")
    parser.add_argument("--write-lock", action="store_true", help="Explicitly refresh candidate release fingerprints")
    parser.add_argument("--out", type=Path, help="Save the validation report")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        references = validate_inputs(root)
        if args.write_reference:
            save_json(root, REFERENCE_PATH, references)
        require(read_json(root, REFERENCE_PATH) == references, "Saved reference answers drifted")
        lock = make_lock(root)
        if args.write_lock:
            save_json(root, LOCK_PATH, lock)
        require(read_json(root, LOCK_PATH) == lock, "Release fingerprint mismatch; review changes before relocking")
        report = {"valid": True, "api_calls": 0, "vehicle_count": len(read_json(root, "configs/evaluation-v1.json")["vehicle_data"]),
                  "scenario_count": len(references["scenarios"]), "checked_turns": 12,
                  "release_status": lock["status"], "input_hashes": lock["files"],
                  "checks": ["vehicle_schema_and_provenance", "constraint_reference_sets",
                             "runner_script_equivalence", "reference_not_sent_to_models", "release_fingerprints"],
                  "eligible_by_scenario": {s["scenario_id"]: [t["eligible_source_ids"] for t in s["turns"]]
                                           for s in references["scenarios"]}}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report = {"valid": False, "api_calls": 0, "error": str(exc)}
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
