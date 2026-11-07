"""Run one non-formal connectivity smoke test for every configured model."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from llm_eval.config import load_model_registry, project_root, registry_as_public_dict
from llm_eval.errors import LLMEvaluationError
from llm_eval.openai_compatible import OpenAICompatibleClient
from llm_eval.prompts import PromptBundle
from llm_eval.structured import SchemaValidatedDecisionClient


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_case(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "scenario" not in data or "vehicle_data" not in data:
        raise ValueError("Smoke case must contain scenario and vehicle_data")
    return data


def run_smoke(
    model_keys: Optional[Sequence[str]] = None,
    case_path: Optional[Path] = None,
    out_path: Optional[Path] = None,
    max_corrections: int = 1,
) -> Dict[str, Any]:
    registry = load_model_registry()
    if model_keys:
        specs = [registry.get(key) for key in model_keys]
    else:
        specs = registry.ordered()

    prompt_bundle = PromptBundle.from_directory()
    source = case_path or (project_root() / "examples" / "smoke_case.json")
    case = _load_case(source)
    messages = prompt_bundle.initial_messages(
        case["scenario"],
        case["vehicle_data"],
    )

    base_client = OpenAICompatibleClient()
    client = SchemaValidatedDecisionClient(
        base_client=base_client,
        prompt_bundle=prompt_bundle,
        max_corrections=max_corrections,
    )

    started_at = _timestamp()
    model_results: List[Dict[str, Any]] = []
    for spec in specs:
        try:
            result = client.complete(spec, messages)
            record = dict(result.as_record())
            record["role"] = spec.role
            record["configured_model_id"] = spec.model_id
            record["parameters"] = dict(spec.parameters)
            model_results.append(record)
        except LLMEvaluationError as exc:
            model_results.append(
                {
                    "model_key": spec.key,
                    "configured_model_id": spec.model_id,
                    "valid": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    record = {
        "record_type": "model_connectivity_smoke_test",
        "formal_evaluation": False,
        "case_id": case["scenario"].get("id", source.stem),
        "started_at": started_at,
        "finished_at": _timestamp(),
        "platform": registry.platform,
        "registry_recorded_on": registry.recorded_on,
        "prompt_version": prompt_bundle.version,
        "prompt_fingerprint": prompt_bundle.fingerprint,
        "case_path": str(source.relative_to(project_root())) if _is_relative(source) else str(source),
        "model_registry": registry_as_public_dict(registry),
        "models": model_results,
        "summary": [
            {
                "model_key": item["model_key"],
                "requested_model": item.get("requested_model"),
                "served_model": item.get("served_model"),
                "valid": item.get("valid", False),
                "finish_reason": item.get("final_response", {}).get("finish_reason"),
                "total_tokens": item.get("total_usage", {}).get("total_tokens"),
                "latency_ms": item.get("total_latency_ms"),
                "correction_attempts": item.get("correction_attempts"),
            }
            for item in model_results
        ],
    }

    destination = out_path or (
        project_root()
        / "runs"
        / "smoke-{}.json".format(datetime.now().strftime("%Y%m%d-%H%M%S"))
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def _is_relative(path: Path) -> bool:
    try:
        path.resolve().relative_to(project_root().resolve())
        return True
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a non-formal car-decision smoke test against configured models."
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Model key to run; repeat to select multiple models. Default: all.",
    )
    parser.add_argument(
        "--case",
        type=Path,
        default=project_root() / "examples" / "smoke_case.json",
        help="Smoke-case JSON path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output JSON path. Default: runs/smoke-<timestamp>.json.",
    )
    parser.add_argument(
        "--max-corrections",
        type=int,
        default=1,
        choices=(0, 1),
        help="Schema correction retries per model (default: 1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local configuration and prompt rendering without API calls.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.dry_run:
        registry = load_model_registry()
        bundle = PromptBundle.from_directory()
        case = _load_case(args.case.resolve())
        messages = bundle.initial_messages(case["scenario"], case["vehicle_data"])
        print(
            json.dumps(
                {
                    "status": "dry-run-ok",
                    "models": [spec.model_id for spec in registry.ordered()],
                    "prompt_version": bundle.version,
                    "prompt_fingerprint": bundle.fingerprint,
                    "rendered_messages": len(messages),
                    "formal_evaluation": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    try:
        record = run_smoke(
            model_keys=args.models,
            case_path=args.case.resolve(),
            out_path=args.out.resolve() if args.out else None,
            max_corrections=args.max_corrections,
        )
    except (LLMEvaluationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            "{}: {}".format(type(exc).__name__, exc),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(record["summary"], ensure_ascii=False, indent=2))
    return 0 if all(item["valid"] for item in record["summary"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

