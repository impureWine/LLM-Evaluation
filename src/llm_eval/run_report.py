"""Inventory evaluation runs and summarize observable execution metrics.

This module never equates a structurally completed conversation with a successful
car recommendation. Quality scores and task success require the frozen rubric.
"""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


FIELDS = (
    "batch", "run_id", "batch_kind", "model", "scenario", "repetition",
    "started_at", "completed", "turns_recorded", "error_type", "elapsed_ms",
    "response_latency_ms", "latency_turns", "prompt_tokens", "completion_tokens", "total_tokens",
    "usage_complete", "source_file",
)


def read_runs(runs_dir, batch_kind="evaluation_candidate", batch=None):
    """Read batch logs without altering them; reject malformed or mixed inputs."""
    runs_dir = Path(runs_dir)
    rows = []
    fingerprints = set()
    if not runs_dir.exists():
        return []
    if not runs_dir.is_dir():
        raise ValueError("Run path is not a directory: {}".format(runs_dir))
    for path in sorted(runs_dir.glob("*/*.json")):
        if batch is not None and path.parent.name != batch:
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("batch_kind") != batch_kind:
            continue
        turns = data.get("turns")
        if not isinstance(turns, list) or not data.get("run_id"):
            raise ValueError("Invalid run record: {}".format(path))
        provenance = tuple(data.get(k) for k in
                           ("manifest_sha256", "prompt_sha256", "scoring_sha256"))
        if any(not value for value in provenance):
            raise ValueError("Missing provenance fingerprint: {}".format(path))
        fingerprints.add(provenance)
        usages = [turn.get("total_usage") for turn in turns if "total_usage" in turn]
        usage_complete = len(usages) == len(turns) and bool(turns) and all(
            isinstance(value, dict) and
            all(isinstance(value.get(k), int)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")) and
            value["total_tokens"] > 0
            for value in usages
        )
        first_error = next((turn.get("error_type") or "invalid_output" for turn in turns
                            if not turn.get("valid")), "")
        measured_turns = [turn for turn in turns
                          if isinstance(turn.get("total_latency_ms"), int)]
        row = {
            "batch": path.parent.name,
            "run_id": data["run_id"],
            "batch_kind": data["batch_kind"],
            "model": data.get("requested_model", ""),
            "scenario": data.get("scenario_id", ""),
            "repetition": data.get("repetition", ""),
            "started_at": data.get("started_at", ""),
            "completed": bool(data.get("completed")) and len(turns) == 4,
            "turns_recorded": len(turns),
            "error_type": first_error,
            "elapsed_ms": data.get("elapsed_ms", ""),
            "response_latency_ms": sum(turn["total_latency_ms"] for turn in measured_turns),
            "latency_turns": len(measured_turns),
            "prompt_tokens": sum(value["prompt_tokens"] for value in usages)
                             if usage_complete else "",
            "completion_tokens": sum(value["completion_tokens"] for value in usages)
                                 if usage_complete else "",
            "total_tokens": sum(value["total_tokens"] for value in usages)
                            if usage_complete else "",
            "usage_complete": usage_complete,
            "source_file": str(path),
        }
        rows.append(row)
    if len(fingerprints) > 1:
        raise ValueError("Runs use different data, prompt or scoring fingerprints; report batches separately")
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["model"], row["scenario"])].append(row)
    result = []
    for (model, scenario), items in sorted(groups.items()):
        elapsed = [r["elapsed_ms"] / 1000 for r in items
                   if isinstance(r["elapsed_ms"], (int, float))]
        tokens = [r["total_tokens"] for r in items if r["usage_complete"]]
        latency_turns = sum(r["latency_turns"] for r in items)
        total_response_ms = sum(r["response_latency_ms"] for r in items)
        result.append({
            "model": model,
            "scenario": scenario,
            "started_tasks": len(items),
            "structure_completed": sum(r["completed"] for r in items),
            "structure_completion_rate": round(sum(r["completed"] for r in items) / len(items), 4),
            "elapsed_samples": len(elapsed),
            "mean_task_seconds": round(statistics.mean(elapsed), 3) if elapsed else None,
            "task_seconds_range": round(max(elapsed) - min(elapsed), 3) if elapsed else None,
            "latency_turns": latency_turns,
            "mean_turn_response_seconds": round(total_response_ms / latency_turns / 1000, 3)
                                          if latency_turns else None,
            "token_samples": len(tokens),
            "mean_total_tokens": round(statistics.mean(tokens), 2) if tokens else None,
            "token_range": max(tokens) - min(tokens) if tokens else None,
        })
    return result


def write_report(rows, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "run_inventory.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"scope": "execution metrics only; quality scores and task success not computed",
               "runs": len(rows), "groups": summarize(rows)}
    (out_dir / "execution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--out-dir", type=Path, default=Path("local/run-report"))
    parser.add_argument("--batch-kind", default="evaluation_candidate")
    parser.add_argument("--batch", help="one batch directory name; use to exclude later reruns")
    args = parser.parse_args(argv)
    try:
        rows = read_runs(args.runs_dir, args.batch_kind, args.batch)
        summary = write_report(rows, args.out_dir)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, "run report: {}\n".format(exc))
    print("{} run records; report: {}".format(summary["runs"], args.out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
