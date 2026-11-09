"""Run the versioned four-turn car decision tasks."""

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from llm_eval.config import load_model_registry, project_root
from llm_eval.comparison import audit_parameter_comparison
from llm_eval.env import load_local_env
from llm_eval.errors import LLMEvaluationError
from llm_eval.models import ChatMessage
from llm_eval.openai_compatible import OpenAICompatibleClient
from llm_eval.prompts import PromptBundle
from llm_eval.structured import SchemaValidatedDecisionClient


def scenario_messages(bundle, scenario, vehicles):
    # Reference answers stay local for scoring.
    initial = {"id": scenario["id"], "user_request": scenario["user_request"]}
    followups = [
        (scenario["second_turn"], scenario["change_rule"]),
        ("请按车型对比有效候选的价格、能源、座位数和辅助驾驶级别。"
         "在每款候选的 why_fit 中逐项列明参数，继续保留来源编号；"
         "并在 parameter_comparison 数组中逐车结构化列出 source_id、model、trim、year、"
         "price_wan、energy、seats、adas，数值必须与车型库完全一致。", ""),
        ("请从仍符合约束的候选中选出一款。返回最终推荐、理由与取舍。", ""),
    ]
    return bundle.initial_messages(initial, vehicles), [
        bundle.followup_message(turn, message, rule)
        for turn, (message, rule) in enumerate(followups, start=2)
    ]


def run_task(client, spec, initial, followups, vehicle_data):
    messages = list(initial)
    turns = []
    started = time.monotonic()
    for turn in range(1, len(followups) + 2):
        if turn > 1:
            messages.append(followups[turn - 2])
        try:
            result = client.complete(spec, messages)
        except LLMEvaluationError as exc:
            turns.append({"turn": turn, "valid": False, "error_type": type(exc).__name__})
            break
        turn_record = {"turn": turn, **result.as_record()}
        payload = result.payload or {}
        comparisons = payload.get("parameter_comparison", [])
        if turn == 3:
            issues = audit_parameter_comparison(payload, vehicle_data)
        else:
            issues = [] if comparisons == [] else ["parameter_comparison must be empty outside turn 3"]
        turn_record["comparison_audit"] = {
            "passed": not issues,
            "issues": issues,
            "checked_rows": len(comparisons) if isinstance(comparisons, list) else 0,
        }
        turns.append(turn_record)
        if not result.valid:
            break
        messages.append(ChatMessage(role="assistant", content=result.final.content))
    return {
        "turns": turns,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "output_contract_completed": len(turns) == 4 and all(
            turn.get("valid") is True
            and turn.get("comparison_audit", {}).get("passed") is True
            for turn in turns
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-disabled-model", action="store_true")
    parser.add_argument("--repetitions", type=int, choices=(1, 3))
    args = parser.parse_args()

    root = project_root()
    manifest = (root / "configs" / "evaluation-v1.json").read_text(encoding="utf-8-sig")
    design = json.loads(manifest)
    registry = load_model_registry()
    specs = [registry.get(key) for key in design["model_keys"]]
    bundle = PromptBundle.from_directory()
    tasks = [
        (scenario["id"], *scenario_messages(bundle, scenario, design["vehicle_data"]))
        for scenario in design["scenarios"]
    ]
    repetitions = args.repetitions or design["repetitions"]
    provenance = {
        "protocol": design["version"],
        "manifest_sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        "prompt_sha256": bundle.fingerprint,
        "scoring_sha256": hashlib.sha256(
            (root / "docs" / "evaluation-protocol-v1.md").read_text(
                encoding="utf-8-sig"
            ).encode("utf-8")
        ).hexdigest(),
    }
    if args.dry_run:
        print(json.dumps({
            **provenance,
            "models": [spec.model_id for spec in specs],
            "scenarios": [task[0] for task in tasks],
            "planned_tasks": len(tasks) * len(specs) * repetitions,
            "turns_per_task": 4,
            "api_calls": 0,
        }, indent=2))
        return 0

    if any(not spec.enabled for spec in specs) and not args.allow_disabled_model:
        parser.error("A candidate is disabled. Confirm access, quota and authorization first.")
    load_local_env()
    if any(not os.getenv(spec.api_key_env) for spec in specs):
        parser.error("Project API credential is missing. Configure it locally in .env.")

    client = SchemaValidatedDecisionClient(OpenAICompatibleClient(), bundle)
    batch = root / "runs" / uuid.uuid4().hex
    batch.mkdir(parents=True)
    contract_completed = 0
    for spec in specs:
        for scenario_id, initial, followups in tasks:
            for repetition in range(1, repetitions + 1):
                run_id = f"{spec.key}-{scenario_id}-{repetition}"
                started_at = datetime.now(timezone.utc).isoformat()
                result = run_task(client, spec, initial, followups, design["vehicle_data"])
                record = {
                    **provenance,
                    "run_id": run_id,
                    "model_key": spec.key,
                    "started_at": started_at,
                    "scenario_id": scenario_id,
                    "repetition": repetition,
                    "platform": registry.platform,
                    "requested_model": spec.model_id,
                    "parameters": dict(spec.parameters),
                    "batch_kind": "pilot" if repetitions == 1 else "evaluation_candidate",
                    **result,
                }
                (batch / f"{run_id}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                contract_completed += result["output_contract_completed"]
    planned = len(tasks) * len(specs) * repetitions
    print(f"{contract_completed}/{planned} four-turn output contracts completed: {batch}")
    return 0 if contract_completed == planned else 2


if __name__ == "__main__":
    raise SystemExit(main())
