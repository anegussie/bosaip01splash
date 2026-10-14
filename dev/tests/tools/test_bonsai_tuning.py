import copy
import unittest

from dev.benchmarks import bonsai_tuning


def round_result(context, milliseconds, thermal="nominal"):
    runs = [
        {
            "metrics_delta": {
                "decode_cycle_ms": milliseconds * 10,
                "decode_output_tokens": 10,
            },
            "response": {
                "choices": [{"message": {"content": "same correct function"}}]
            },
            "draft_acceptance": 0.7,
        }
        for _ in range(3)
    ]
    return {
        "context": context,
        "coding": {"runs": runs},
        "context_workload": {"cold": {"seconds": 30}, "cached": {"seconds": 3}},
        "start": {"status": {"thermal_state": thermal}},
        "after": {"thermal_state": thermal},
    }


class BonsaiTuningTests(unittest.TestCase):
    def test_quiet_matched_gain_uses_abba_bound(self):
        result = bonsai_tuning.compare(
            [
                round_result("24K", 30),
                round_result("8K", 24),
                round_result("8K", 24),
                round_result("24K", 30),
            ]
        )
        self.assertTrue(result["8K"]["speedup_supported"])
        self.assertAlmostEqual(result["8K"]["coding_tok_per_second"], 1000 / 24)
        self.assertAlmostEqual(
            result["8K"]["comparison_to_baseline"]["regression"], -0.2
        )

    def test_noise_or_thermal_drift_prevents_speed_claim(self):
        for rows in (
            [
                round_result("24K", 30),
                round_result("8K", 20),
                round_result("8K", 20),
                round_result("24K", 34),
            ],
            [
                round_result("24K", 30),
                round_result("8K", 20, "fair"),
                round_result("8K", 20),
                round_result("24K", 30),
            ],
        ):
            self.assertFalse(bonsai_tuning.compare(rows)["8K"]["speedup_supported"])

    def test_changed_outputs_or_acceptance_prevents_claim(self):
        rows = [
            round_result("24K", 30),
            round_result("8K", 20),
            round_result("8K", 20),
            round_result("24K", 30),
        ]
        for field in ("output", "acceptance"):
            altered = copy.deepcopy(rows)
            for row in altered[1:3]:
                if field == "output":
                    row["coding"]["runs"][0]["response"]["choices"][0]["message"][
                        "content"
                    ] = "changed function"
                else:
                    row["coding"]["runs"][0]["draft_acceptance"] = 0.6
            self.assertFalse(bonsai_tuning.compare(altered)["8K"]["speedup_supported"])

    def test_single_round_is_characterization_only(self):
        result = bonsai_tuning.compare(
            [round_result("24K", 30), round_result("8K", 20)]
        )
        self.assertFalse(result["8K"]["speed_verdict_eligible"])
        self.assertFalse(result["8K"]["speedup_supported"])


if __name__ == "__main__":
    unittest.main()
