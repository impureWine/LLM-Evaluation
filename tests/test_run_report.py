"""Check that run reporting preserves the boundary between execution and quality."""

import json
import tempfile
import unittest
from pathlib import Path

from llm_eval.run_report import read_runs, summarize, write_report


class RunReportTests(unittest.TestCase):
    def make_run(self, root, batch, name, *, complete=True, fingerprint="same", kind="evaluation_candidate"):
        folder = root / batch
        folder.mkdir(exist_ok=True)
        turns = [{"turn": i, "valid": True, "total_latency_ms": 100,
                  "total_usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                  "total_tokens": 15}} for i in range(1, 5 if complete else 3)]
        if not complete:
            turns[-1] = {"turn": 2, "valid": False, "error_type": "TimeoutError"}
        record = {"run_id": name, "batch_kind": kind, "requested_model": "glm-test",
                  "scenario_id": "city", "repetition": 1, "started_at": "2026-11-08T00:00:00Z",
                  "completed": complete, "elapsed_ms": 1200, "turns": turns,
                  "manifest_sha256": fingerprint, "prompt_sha256": "p", "scoring_sha256": "s"}
        (folder / (name + ".json")).write_text(json.dumps(record), encoding="utf-8")

    def test_failed_run_counts_but_missing_usage_does_not_become_zero_tokens(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_run(root, "batch", "complete")
            self.make_run(root, "batch", "failed", complete=False)
            self.make_run(root, "pilot", "pilot", kind="pilot")
            rows = read_runs(root)
            summary = summarize(rows)[0]
            self.assertEqual(summary["started_tasks"], 2)
            self.assertEqual(summary["structure_completed"], 1)
            self.assertEqual(summary["token_samples"], 1)
            self.assertEqual(summary["mean_total_tokens"], 60)
            self.assertEqual(summary["latency_turns"], 5)
            self.assertEqual(summary["mean_turn_response_seconds"], 0.1)
            self.assertIn("task success not computed", write_report(rows, root / "out")["scope"])

    def test_mixed_fingerprints_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_run(root, "a", "one", fingerprint="one")
            self.make_run(root, "b", "two", fingerprint="two")
            with self.assertRaisesRegex(ValueError, "different"):
                read_runs(root)
            self.assertEqual(len(read_runs(root, batch="a")), 1)

    def test_absent_run_directory_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(read_runs(Path(temp) / "missing"), [])


if __name__ == "__main__":
    unittest.main()
