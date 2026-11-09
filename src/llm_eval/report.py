"""Extract and summarize compatible formal evaluation run records."""

import argparse
import csv
import hashlib
import html
import json
import statistics
from pathlib import Path

from llm_eval.config import project_root


SCORE_COMPONENTS = {
    "constraint_adherence_40": 40,
    "multi_turn_consistency_25": 25,
    "instruction_following_15": 15,
    "factuality_20": 20,
}
SCORE_FIELDS = ("run_id", *SCORE_COMPONENTS, "reviewer", "notes")


VEHICLE_FIELDS = ("model", "trim", "year", "price_wan", "energy", "seats", "adas")
EXTRACTION_FIELDS = {
    "candidates": (
        "run_id", "model_key", "requested_model", "scenario_id", "repetition", "turn",
        "source_id", "model", "trim", "year", "price_wan", "eligible",
        "expected_model", "expected_trim", "expected_year", "expected_price_wan",
        "evidence_ids", "fixed_vehicle_match", "meets_constraints", "why_fit", "risks",
    ),
    "comparisons": (
        "run_id", "model_key", "requested_model", "scenario_id", "repetition",
        "source_id", *VEHICLE_FIELDS,
        *("expected_" + field for field in VEHICLE_FIELDS),
        "eligible", "mismatch_fields", "facts_match",
    ),
    "recommendations": (
        "run_id", "model_key", "requested_model", "scenario_id", "repetition",
        "source_id", "model", "trim", "year", "eligible", "reason", "tradeoffs",
    ),
    "runs": (
        "run_id", "model_key", "requested_model", "scenario_id", "repetition",
        "output_contract_completed", "turns_recorded", "elapsed_ms", "total_tokens", "token_turns_missing",
        "candidate_rows", "comparison_rows", "comparison_audit_passed", "recommended_source_id",
        "recommendation_eligible", "failure_types", *SCORE_COMPONENTS, "total_score", "reviewer",
    ),
    "models": (
        "model_key", "requested_model", "scenario_id", "expected_repetitions", "observed_n",
        "output_contract_completed_n", "four_turn_output_contract_rate", "elapsed_n", "mean_elapsed_ms", "median_elapsed_ms",
        "token_count_n", "mean_total_tokens", "candidate_rows", "eligible_candidate_rows",
        "comparison_rows", "matching_comparison_rows", "comparison_checked_runs",
        "comparison_audit_passed_runs", "comparison_audit_missing_runs", "comparison_audit_pass_rate",
        "eligible_final_recommendations",
        "scored_runs", "mean_total_score", "truth_review_status",
    ),
}


def _json_read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read_scores(path, run_ids):
    if path is None:
        return {}
    scores = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing_headers = set(SCORE_FIELDS) - set(reader.fieldnames or [])
        if missing_headers:
            raise ValueError("Score CSV is missing columns: {}".format(", ".join(sorted(missing_headers))))
        for row in reader:
            run_id = (row.get("run_id") or "").strip()
            if not run_id:
                raise ValueError("Score rows must include run_id")
            if run_id not in run_ids:
                raise ValueError("Score file contains unknown run_id: {}".format(run_id))
            if run_id in scores:
                raise ValueError("Score file contains duplicate run_id: {}".format(run_id))
            raw = {field: (row.get(field) or "").strip() for field in SCORE_COMPONENTS}
            present = [bool(value) for value in raw.values()]
            if any(present) and not all(present):
                raise ValueError("Score row {} must provide all four score components".format(run_id))
            values = {}
            if all(present):
                for field, maximum in SCORE_COMPONENTS.items():
                    try:
                        score = int(raw[field])
                    except ValueError as exc:
                        raise ValueError("{} must be an integer score".format(field)) from exc
                    if not 0 <= score <= maximum:
                        raise ValueError("{} must be between 0 and {}".format(field, maximum))
                    values[field] = score
            else:
                values = {field: "" for field in SCORE_COMPONENTS}
            values["reviewer"] = (row.get("reviewer") or "").strip()
            if all(present) and not values["reviewer"]:
                raise ValueError("Score row {} must name a reviewer".format(run_id))
            values["notes"] = (row.get("notes") or "").strip()
            scores[run_id] = values
    return scores


def _csv_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _same_fields(left, right, fields):
    return all(
        left.get(field) == right.get(field)
        and type(left.get(field)) is type(right.get(field))
        for field in fields
    )


def _source_for_candidate(candidate, vehicles):
    ids = candidate.get("evidence_ids")
    if not isinstance(ids, list) or len(ids) != 1:
        return None
    source_id = ids[0]
    vehicle = vehicles.get(source_id)
    if vehicle is None:
        return None
    return source_id, vehicle


def _source_for_recommendation(recommendation, vehicles):
    if not isinstance(recommendation, dict):
        return None
    matches = [
        (source_id, vehicle) for source_id, vehicle in vehicles.items()
        if _same_fields(recommendation, vehicle, ("model", "trim", "year"))
    ]
    return matches[0] if len(matches) == 1 else None


def _turn(run, number):
    turns = run.get("turns", [])
    if not isinstance(turns, list):
        return None
    for turn in turns:
        if isinstance(turn, dict) and turn.get("turn") == number:
            return turn
    return None


def _payload(turn):
    value = turn.get("parsed_output") if isinstance(turn, dict) else None
    return value if isinstance(value, dict) else {}


def _extract_run(run, references, vehicles):
    scenario_id = run.get("scenario_id", "")
    run_id = run.get("run_id", "")
    model_key = run.get("model_key") or ((_turn(run, 1) or {}).get("model_key", ""))
    if not model_key and scenario_id and run_id.endswith("-{}-{}".format(scenario_id, run.get("repetition", ""))):
        model_key = run_id[:-(len(scenario_id) + len(str(run.get("repetition", ""))) + 2)]
    base = {
        "run_id": run_id,
        "model_key": model_key,
        "requested_model": run.get("requested_model", ""),
        "scenario_id": scenario_id,
        "repetition": run.get("repetition", ""),
    }
    scenario_refs = references.get(base["scenario_id"], [])
    candidates, comparisons, recommendations = [], [], []
    for number in (1, 2):
        turn = _turn(run, number)
        payload = _payload(turn)
        allowed = set(scenario_refs[number - 1]) if len(scenario_refs) >= number else set()
        for candidate in payload.get("candidate_cars", []):
            if not isinstance(candidate, dict):
                continue
            resolved = _source_for_candidate(candidate, vehicles)
            source_id, vehicle = resolved if resolved else ("", {})
            fixed_match = bool(resolved and _same_fields(candidate, vehicle, VEHICLE_FIELDS[:4]))
            candidates.append({
                **base, "turn": number, "source_id": source_id,
                **{field: candidate.get(field, "") for field in VEHICLE_FIELDS[:4]},
                **{"expected_" + field: vehicle.get(field, "") for field in VEHICLE_FIELDS[:4]},
                "eligible": bool(fixed_match and source_id in allowed),
                "evidence_ids": candidate.get("evidence_ids", []),
                "fixed_vehicle_match": fixed_match,
                "meets_constraints": candidate.get("meets_constraints", []),
                "why_fit": candidate.get("why_fit", ""),
                "risks": candidate.get("risks", []),
            })

    turn_three = _turn(run, 3)
    compare_payload = _payload(turn_three)
    allowed = set(scenario_refs[2]) if len(scenario_refs) >= 3 else set()
    for row in compare_payload.get("parameter_comparison", []):
        if not isinstance(row, dict):
            continue
        source_id = row.get("source_id", "")
        vehicle = vehicles.get(source_id, {})
        mismatch = [field for field in VEHICLE_FIELDS if not _same_fields(row, vehicle, (field,))]
        comparisons.append({
            **base, "source_id": source_id,
            **{field: row.get(field, "") for field in VEHICLE_FIELDS},
            **{"expected_" + field: vehicle.get(field, "") for field in VEHICLE_FIELDS},
            "eligible": source_id in allowed,
            "mismatch_fields": mismatch,
            "facts_match": bool(vehicle and not mismatch),
        })

    turn_four = _turn(run, 4)
    final = _payload(turn_four).get("final_recommendation")
    resolved = _source_for_recommendation(final, vehicles)
    source_id, vehicle = resolved if resolved else ("", {})
    final_allowed = set(scenario_refs[3]) if len(scenario_refs) >= 4 else set()
    final = final if isinstance(final, dict) else {}
    recommendations.append({
        **base, "source_id": source_id,
        **{field: final.get(field, "") for field in ("model", "trim", "year")},
        "eligible": bool(source_id and source_id in final_allowed),
        "reason": final.get("reason", ""),
        "tradeoffs": final.get("tradeoffs", []),
    })

    recorded_turns = run.get("turns", [])
    if not isinstance(recorded_turns, list):
        recorded_turns = []
    tokens = []
    missing_token_turns = max(0, 4 - len(recorded_turns))
    for turn in recorded_turns:
        usage = turn.get("total_usage")
        if (isinstance(usage, dict) and usage.get("reported") is True
                and isinstance(usage.get("total_tokens"), int)):
            tokens.append(usage["total_tokens"])
        else:
            missing_token_turns += 1
    comparison_audit = turn_three.get("comparison_audit", {}) if turn_three else {}
    if not isinstance(comparison_audit, dict):
        comparison_audit = {}
    recommendation_row = recommendations[0] if recommendations else {}
    failure_types = sorted({
        turn["error_type"] for turn in recorded_turns
        if isinstance(turn, dict) and turn.get("error_type")
    })
    run_row = {
        **base,
        "output_contract_completed": bool(run.get("output_contract_completed")),
        "turns_recorded": len(recorded_turns),
        "elapsed_ms": run.get("elapsed_ms", ""),
        "total_tokens": sum(tokens) if tokens and missing_token_turns == 0 else "",
        "token_turns_missing": missing_token_turns,
        "candidate_rows": len(candidates),
        "comparison_rows": len(comparisons),
        "comparison_audit_passed": comparison_audit.get("passed", ""),
        "recommended_source_id": recommendation_row.get("source_id", ""),
        "recommendation_eligible": recommendation_row.get("eligible", ""),
        "failure_types": failure_types,
    }
    return candidates, comparisons, recommendations, run_row


def _compatible_records(runs_dir, expected_hashes):
    included, excluded = [], []
    if not runs_dir.exists():
        return included, excluded
    batch_files = {}
    for path in sorted(runs_dir.rglob("*.json")):
        batch_files.setdefault(path.parent, []).append(path)
    compatible_batches = []
    for batch_dir, paths in batch_files.items():
        batch_records = []
        for path in paths:
            try:
                record = _json_read(path)
            except (OSError, json.JSONDecodeError) as exc:
                excluded.append({"path": str(path), "reason": "invalid JSON: {}".format(exc)})
                continue
            if not isinstance(record, dict) or "run_id" not in record:
                continue
            if record.get("batch_kind") != "evaluation_candidate":
                excluded.append({"path": str(path), "run_id": record.get("run_id", ""),
                                 "reason": "not an evaluation_candidate batch"})
                continue
            differences = [
                key for key, value in expected_hashes.items()
                if record.get(key) != value
            ]
            if differences:
                excluded.append({"path": str(path), "run_id": record.get("run_id", ""),
                                 "reason": "incompatible fingerprints: {}".format(", ".join(differences))})
                continue
            batch_records.append(record)
        if batch_records:
            compatible_batches.append((batch_dir, batch_records))
    if len(compatible_batches) > 1:
        raise ValueError(
            "Multiple compatible evaluation batches found; pass --runs with one batch directory"
        )
    if compatible_batches:
        included = compatible_batches[0][1]
        run_ids = [record["run_id"] for record in included]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("Run IDs must be unique within one evaluation batch")
    return included, excluded


def _model_summary(root, records, design, run_rows, candidates, comparisons, recommendations):
    model_config = _json_read(root / "configs" / "models.json")
    models = {item["key"]: item["model_id"] for item in model_config["models"]}
    scenario_ids = [scenario["id"] for scenario in design["scenarios"]]
    result = []
    for model_key, requested_model in models.items():
        for scenario_id in scenario_ids:
            group = [r for r in records if r.get("model_key") == model_key and r.get("scenario_id") == scenario_id]
            task_rows = [r for r in run_rows if r["model_key"] == model_key and r["scenario_id"] == scenario_id]
            latencies = [r["elapsed_ms"] for r in task_rows if isinstance(r["elapsed_ms"], (int, float))]
            token_values = [r["total_tokens"] for r in task_rows if isinstance(r["total_tokens"], int)]
            candidate_rows = [r for r in candidates if r["model_key"] == model_key and r["scenario_id"] == scenario_id]
            comparison_rows = [r for r in comparisons if r["model_key"] == model_key and r["scenario_id"] == scenario_id]
            final_rows = [r for r in recommendations if r["model_key"] == model_key and r["scenario_id"] == scenario_id]
            comparison_runs = [
                r for r in task_rows
                if isinstance(r["comparison_audit_passed"], bool)
            ]
            comparison_passed = sum(r["comparison_audit_passed"] is True for r in comparison_runs)
            scored_rows = [r for r in task_rows if isinstance(r.get("total_score"), int)]
            completed = sum(bool(r.get("output_contract_completed")) for r in group)
            count = len(group)
            result.append({
                "model_key": model_key,
                "requested_model": requested_model,
                "scenario_id": scenario_id,
                "expected_repetitions": design["repetitions"],
                "observed_n": count,
                "output_contract_completed_n": completed,
                "four_turn_output_contract_rate": completed / count if count else "",
                "elapsed_n": len(latencies),
                "mean_elapsed_ms": statistics.mean(latencies) if latencies else "",
                "median_elapsed_ms": statistics.median(latencies) if latencies else "",
                "token_count_n": len(token_values),
                "mean_total_tokens": statistics.mean(token_values) if token_values else "",
                "candidate_rows": len(candidate_rows),
                "eligible_candidate_rows": sum(bool(r["eligible"]) for r in candidate_rows),
                "comparison_rows": len(comparison_rows),
                "matching_comparison_rows": sum(bool(r["facts_match"]) for r in comparison_rows),
                "comparison_checked_runs": len(comparison_runs),
                "comparison_audit_passed_runs": comparison_passed,
                "comparison_audit_missing_runs": len(task_rows) - len(comparison_runs),
                "comparison_audit_pass_rate": comparison_passed / len(comparison_runs) if comparison_runs else "",
                "eligible_final_recommendations": sum(bool(r["eligible"]) for r in final_rows),
                "scored_runs": len(scored_rows),
                "mean_total_score": statistics.mean(r["total_score"] for r in scored_rows) if scored_rows else "",
                "truth_review_status": (
                    "human_review_complete" if count and len(scored_rows) == count
                    else "human_review_partial_or_pending"
                ),
            })
    return result


def _chart_svg(rows):
    colors = ("#2563eb", "#e76f51")
    model_keys = list(dict.fromkeys(row["model_key"] for row in rows))
    models = [next(r["requested_model"] for r in rows if r["model_key"] == key) for key in model_keys]
    scenarios = list(dict.fromkeys(row["scenario_id"] for row in rows))
    if not any(row["observed_n"] for row in rows):
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="180" viewBox="0 0 760 180">'
            '<rect width="760" height="180" fill="#fff"/><text x="28" y="48" font-size="20" '
            'font-family="sans-serif" fill="#1f2937">无可用正式运行记录，暂不绘制模型比较图</text>'
            '<text x="28" y="86" font-size="14" font-family="sans-serif" fill="#5b6573">'
            '联调批次和冒烟测试不纳入正式汇总。</text></svg>\n'
        )

    width, height = 920, 430
    left, right, top = 215, 34, 74
    plot_width = width - left - right
    row_gap = 96
    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width, height, width, height),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="{}" y="34" font-size="22" font-family="sans-serif" fill="#17212b">四轮输出契约完成率与平均耗时</text>'.format(left),
        '<text x="{}" y="57" font-size="13" font-family="sans-serif" fill="#58636e">结构和比较表均通过；括号为实际 n，完成率不是满分率</text>'.format(left),
    ]
    for model_index, model in enumerate(models):
        x = left + model_index * 230
        body.append('<rect x="{}" y="68" width="14" height="14" fill="{}"/>'.format(x, colors[model_index % len(colors)]))
        body.append('<text x="{}" y="80" font-size="12" font-family="sans-serif" fill="#344054">{}</text>'.format(x + 20, html.escape(model)))
    for scenario_index, scenario in enumerate(scenarios):
        y = top + scenario_index * row_gap
        body.append('<text x="{}" y="{}" text-anchor="end" font-size="14" font-family="sans-serif" fill="#344054">{}</text>'.format(left - 14, y + 22, html.escape(scenario)))
        for model_index, model_key in enumerate(model_keys):
            row = next(r for r in rows if r["model_key"] == model_key and r["scenario_id"] == scenario)
            count = row["observed_n"]
            complete_rate = row["four_turn_output_contract_rate"]
            latency = row["mean_elapsed_ms"]
            bar_y = y + model_index * 28
            if count and complete_rate != "":
                bar_width = max(1, plot_width * complete_rate)
                body.append('<rect x="{}" y="{}" width="{:.1f}" height="16" rx="2" fill="{}"/>'.format(left, bar_y, bar_width, colors[model_index % len(colors)]))
                latency_text = "{:.1f}s".format(latency / 1000) if isinstance(latency, (int, float)) else "n/a"
                body.append('<text x="{}" y="{}" font-size="12" font-family="sans-serif" fill="#344054">{:.0f}% (n={}) · {} 平均</text>'.format(min(left + bar_width + 8, width - right - 190), bar_y + 13, complete_rate * 100, count, latency_text))
            else:
                body.append('<text x="{}" y="{}" font-size="12" font-family="sans-serif" fill="#87909c">无运行记录</text>'.format(left, bar_y + 13))
        body.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#e5e7eb"/>'.format(left, y + row_gap - 8, width - right, y + row_gap - 8))
    body.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#94a3b8"/>'.format(left, height - 35, width - right, height - 35))
    for tick in (0, 25, 50, 75, 100):
        x = left + plot_width * tick / 100
        body.append('<line x1="{:.1f}" y1="{}" x2="{:.1f}" y2="{}" stroke="#e5e7eb"/>'.format(x, top - 8, x, height - 35))
        body.append('<text x="{:.1f}" y="{}" text-anchor="middle" font-size="11" font-family="sans-serif" fill="#667085">{}%</text>'.format(x, height - 14, tick))
    body.append('</svg>')
    return "".join(body) + "\n"


def _score_svg(rows):
    colors = ("#2563eb", "#e76f51")
    model_keys = list(dict.fromkeys(row["model_key"] for row in rows))
    scenarios = list(dict.fromkeys(row["scenario_id"] for row in rows))
    width, height = 900, 310
    left, right, top = 205, 35, 66
    plot_width = width - left - right
    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width, height, width, height),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="{}" y="32" font-size="21" font-family="sans-serif" fill="#17212b">人工复核总分（满分 100）</text>'.format(left),
        '<text x="{}" y="53" font-size="12" font-family="sans-serif" fill="#58636e">仅汇总 reviewed-scores.csv 中已填写的评分；样本数随模型和场景显示</text>'.format(left),
    ]
    names = {
        model_key: next(r["requested_model"] for r in rows if r["model_key"] == model_key)
        for model_key in model_keys
    }
    for model_index, model_key in enumerate(model_keys):
        x = left + model_index * 230
        body.append('<rect x="{}" y="62" width="14" height="14" fill="{}"/>'.format(x, colors[model_index % len(colors)]))
        body.append('<text x="{}" y="74" font-size="12" font-family="sans-serif" fill="#344054">{}</text>'.format(x + 20, html.escape(names[model_key])))
    for scenario_index, scenario in enumerate(scenarios):
        y = top + scenario_index * 72
        body.append('<text x="{}" y="{}" text-anchor="end" font-size="14" font-family="sans-serif" fill="#344054">{}</text>'.format(left - 14, y + 18, html.escape(scenario)))
        for model_index, model_key in enumerate(model_keys):
            row = next(r for r in rows if r["model_key"] == model_key and r["scenario_id"] == scenario)
            score = row["mean_total_score"]
            n = row["scored_runs"]
            bar_y = y + model_index * 24
            if n and isinstance(score, (int, float)):
                bar_width = max(1, plot_width * score / 100)
                body.append('<rect x="{}" y="{}" width="{:.1f}" height="15" rx="2" fill="{}"/>'.format(left, bar_y, bar_width, colors[model_index % len(colors)]))
                body.append('<text x="{}" y="{}" font-size="12" font-family="sans-serif" fill="#344054">{:.1f} (n={})</text>'.format(min(left + bar_width + 8, width - right - 90), bar_y + 12, score, n))
            else:
                body.append('<text x="{}" y="{}" font-size="12" font-family="sans-serif" fill="#87909c">待人工评分</text>'.format(left, bar_y + 12))
    for tick in (0, 25, 50, 75, 100):
        x = left + plot_width * tick / 100
        body.append('<line x1="{:.1f}" y1="{}" x2="{:.1f}" y2="{}" stroke="#e5e7eb"/>'.format(x, top - 6, x, height - 30))
        body.append('<text x="{:.1f}" y="{}" text-anchor="middle" font-size="11" font-family="sans-serif" fill="#667085">{}</text>'.format(x, height - 10, tick))
    body.append('</svg>')
    return "".join(body) + "\n"


def build_report(root, runs_dir=None, output_dir=None, scores_path=None):
    root = Path(root)
    runs_dir = Path(runs_dir or root / "runs")
    output_dir = Path(output_dir or root / "evidence" / "results")
    design = _json_read(root / "configs" / "evaluation-v1.json")
    references_data = _json_read(root / "data" / "reference-answers-v1.json")
    vehicles_data = design["vehicle_data"]
    vehicles = {v["source_id"]: v for v in vehicles_data}
    references = {
        scenario["scenario_id"]: [turn["eligible_source_ids"] for turn in scenario["turns"]]
        for scenario in references_data["scenarios"]
    }
    hashes = {
        "manifest_sha256": hashlib.sha256((root / "configs" / "evaluation-v1.json").read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest(),
        "prompt_sha256": "",
        "scoring_sha256": hashlib.sha256((root / "docs" / "evaluation-protocol-v1.md").read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest(),
    }
    from llm_eval.prompts import PromptBundle
    hashes["prompt_sha256"] = PromptBundle.from_directory(root / "prompts").fingerprint
    expected_hashes = hashes
    records, excluded = _compatible_records(runs_dir, expected_hashes)

    candidate_rows, comparison_rows, recommendation_rows, run_rows = [], [], [], []
    for record in records:
        extracted = _extract_run(record, references, vehicles)
        candidate_rows.extend(extracted[0])
        comparison_rows.extend(extracted[1])
        recommendation_rows.extend(extracted[2])
        run_rows.append(extracted[3])
    score_values = _read_scores(scores_path, {row["run_id"] for row in run_rows})
    for row in run_rows:
        score = score_values.get(row["run_id"], {})
        row.update(score)
        components = [row.get(field, "") for field in SCORE_COMPONENTS]
        row["total_score"] = sum(components) if components and all(isinstance(value, int) for value in components) else ""
    model_rows = _model_summary(root, records, design, run_rows, candidate_rows, comparison_rows, recommendation_rows)
    expected_cells = {
        (model_key, scenario["id"], str(repetition))
        for model_key in design["model_keys"]
        for scenario in design["scenarios"]
        for repetition in range(1, design["repetitions"] + 1)
    }
    cell_counts = {}
    for record in records:
        cell = (record.get("model_key", ""), record.get("scenario_id", ""), str(record.get("repetition", "")))
        cell_counts[cell] = cell_counts.get(cell, 0) + 1
    observed_cells = set(cell_counts)
    missing_cells = sorted(expected_cells - observed_cells)
    unexpected_cells = sorted(observed_cells - expected_cells, key=str)
    duplicate_cells = sorted((cell for cell, count in cell_counts.items() if count > 1), key=str)
    complete_matrix = bool(records) and not missing_cells and not unexpected_cells and not duplicate_cells

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, key, rows in (
        ("candidate-extraction.csv", "candidates", candidate_rows),
        ("parameter-comparison.csv", "comparisons", comparison_rows),
        ("final-recommendations.csv", "recommendations", recommendation_rows),
        ("run-summary.csv", "runs", run_rows),
        ("model-summary.csv", "models", model_rows),
        ("reviewed-scores.csv", None, run_rows),
    ):
        fields = SCORE_FIELDS if key is None else EXTRACTION_FIELDS[key]
        _write_csv(output_dir / filename, fields,
                   [{k: _csv_value(v) for k, v in row.items()} for row in rows])
    score_template_path = output_dir / "score-template.csv"
    preserve_template = scores_path is not None and Path(scores_path).resolve() == score_template_path.resolve()
    if not preserve_template:
        template_rows = [
            {"run_id": row["run_id"], **{field: "" for field in SCORE_COMPONENTS}, "reviewer": "", "notes": ""}
            for row in run_rows
        ]
        _write_csv(score_template_path, SCORE_FIELDS, template_rows)
    svg = _chart_svg(model_rows)
    (output_dir / "model-comparison.svg").write_text(svg, encoding="utf-8")
    (output_dir / "score-comparison.svg").write_text(_score_svg(model_rows), encoding="utf-8")
    report = {
        "status": (
            "complete_matrix_ready_for_review" if complete_matrix
            else "partial_matrix" if records
            else "no_compatible_evaluation_runs"
        ),
        "record_count": len(records),
        "scored_record_count": sum(isinstance(row.get("total_score"), int) for row in run_rows),
        "expected_tasks": len(design["model_keys"]) * len(design["scenarios"]) * design["repetitions"],
        "missing_matrix_cells": [list(cell) for cell in missing_cells],
        "unexpected_matrix_cells": [list(cell) for cell in unexpected_cells],
        "duplicate_matrix_cells": [list(cell) for cell in duplicate_cells],
        "included_batch_kind": "evaluation_candidate",
        "excluded_records": excluded,
        "prompt_sha256": expected_hashes["prompt_sha256"],
        "manifest_sha256": expected_hashes["manifest_sha256"],
        "scoring_sha256": expected_hashes["scoring_sha256"],
        "truth_scoring": "Human review required; no 100-point totals are inferred from incomplete text evidence.",
        "outputs": ["candidate-extraction.csv", "parameter-comparison.csv",
                    "final-recommendations.csv", "run-summary.csv", "model-summary.csv",
                    "reviewed-scores.csv", "score-template.csv", "model-comparison.svg",
                    "score-comparison.svg"],
    }
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, help="Run directory to read (default: <repo>/runs)")
    parser.add_argument("--out", type=Path, help="Output directory (default: <repo>/evidence/results)")
    parser.add_argument("--scores", type=Path, help="Optional CSV of human-reviewed rubric scores")
    args = parser.parse_args(argv)
    root = project_root()
    try:
        report = build_report(root, args.runs, args.out, args.scores)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
