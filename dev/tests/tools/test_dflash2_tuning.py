"""A faster aggregate must not hide changed output or a noisy/regressed task."""

import copy
import signal
import threading
import unittest
from unittest import mock

from dev.benchmarks.dflash2_tuning import compare, guard_primary, released_primary


def phases():
    result = []
    for milliseconds in (10, 8, 8, 10):
        runs = []
        for key in ("4096-chunked", "20480-merge_intervals", "tool-call"):
            runs.append(
                {
                    "key": key,
                    "cycle_ms_per_token": milliseconds,
                    "seconds": milliseconds,
                    "correct": True,
                    "response": {"choices": [{"message": {"content": "unchanged"}}]},
                    "thermal": ["fair", "fair"],
                    "draft_acceptance": 0.5,
                }
            )
        result.append(
            {
                "runs": runs,
                "target_artifact_digest": "same-target-file",
                "before": {
                    "identity": {
                        "cache": {"build_id": "same-build"},
                        "kv": {"target_model_sha256": "same-target"},
                    }
                },
            }
        )
    return result


class DFlashTuningTests(unittest.TestCase):
    def test_matched_correct_improvement_is_eligible(self):
        result = compare(phases())
        self.assertTrue(result["eligible"])
        self.assertTrue(result["candidate_wins"])

    def test_output_drift_disqualifies_an_apparent_speedup(self):
        rows = phases()
        rows[1]["runs"][0]["response"]["choices"][0]["message"]["content"] = "different"
        result = compare(rows)
        self.assertFalse(result["eligible"])
        self.assertFalse(result["candidate_wins"])

    def test_thermal_drift_disqualifies_an_apparent_speedup(self):
        rows = phases()
        rows[1]["runs"][0]["thermal"] = ["nominal", "fair"]
        self.assertFalse(compare(rows)["eligible"])

    def test_sampled_output_can_differ_when_behavior_checks_pass(self):
        rows = phases()
        for phase in rows:
            for row in phase["runs"]:
                row["temperature"] = 0.7
        rows[1]["runs"][0]["response"]["choices"][0]["message"]["content"] = "different"
        self.assertTrue(compare(rows)["candidate_wins"])
        rows[1]["runs"][0]["correct"] = False
        self.assertFalse(compare(rows)["candidate_wins"])

    def test_one_regression_is_not_hidden_by_other_gains(self):
        rows = phases()
        for phase in rows[1:3]:
            phase["runs"][0]["cycle_ms_per_token"] = 12
            phase["runs"][1]["cycle_ms_per_token"] = 2
        self.assertFalse(compare(rows)["candidate_wins"])

    def test_one_noisy_task_is_not_hidden_by_aggregate(self):
        rows = phases()
        rows[1]["runs"][0]["cycle_ms_per_token"] = 6
        rows[2]["runs"][0]["cycle_ms_per_token"] = 10
        self.assertFalse(compare(rows)["eligible"])

    def test_incomplete_comparison_cannot_select_candidate(self):
        self.assertFalse(compare(copy.deepcopy(phases()[:3]))["eligible"])

    def test_a_changed_build_or_target_cannot_select_candidate(self):
        rows = phases()
        rows[1]["before"]["identity"]["cache"]["build_id"] = "different"
        self.assertFalse(compare(rows)["candidate_wins"])
        rows = phases()
        rows[1]["target_artifact_digest"] = "different"
        self.assertFalse(compare(rows)["candidate_wins"])

    def test_different_assembly_identity_can_share_the_same_target_artifact(self):
        rows = phases()
        for phase in rows[1:3]:
            phase["before"]["identity"]["kv"]["target_model_sha256"] = (
                "candidate-assembly"
            )
        self.assertTrue(compare(rows)["candidate_wins"])

    def test_slower_requests_disqualify_faster_decode(self):
        rows = phases()
        for phase in rows[1:3]:
            phase["runs"][0]["seconds"] = 20
        self.assertFalse(compare(rows)["candidate_wins"])

    def test_only_a_released_idle_primary_can_share_the_machine(self):
        status = {
            "weights": {"released": True},
            "active_requests": [],
            "transport": {"pending": 0, "frontend_waiting": 0},
            "requests": {"submitted": 10},
        }
        with mock.patch("dev.benchmarks.dflash2_tuning.request", return_value=status):
            self.assertEqual(released_primary(), 10)
            status["weights"]["released"] = False
            with self.assertRaisesRegex(RuntimeError, "needs the GPU"):
                released_primary()
            status["weights"]["released"] = True
            status["transport"]["pending"] = 1
            with self.assertRaisesRegex(RuntimeError, "pending requests"):
                released_primary()

    def test_primary_resume_terminates_the_benchmark_process_group(self):
        process = mock.Mock(pid=123456)
        process.poll.return_value = None
        stopped = threading.Event()
        with (
            mock.patch(
                "dev.benchmarks.dflash2_tuning.released_primary", side_effect=[10, 11]
            ),
            mock.patch(
                "dev.benchmarks.dflash2_tuning.os.killpg",
                side_effect=lambda *_: stopped.set(),
            ) as kill,
            self.assertRaisesRegex(RuntimeError, "stopped to spare the normal server"),
        ):
            with guard_primary(process, True):
                self.assertTrue(stopped.wait(timeout=3))
        kill.assert_called_once_with(123456, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
