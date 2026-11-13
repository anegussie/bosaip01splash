import unittest
from pathlib import Path

from dev.benchmarks import option21_arms


def snapshot(prefill_tokens, decode_tokens, decode_ms, reads, routed, work_ms, resident):
    return {
        "requests": {"submitted": decode_tokens, "completed": decode_tokens},
        "metrics": {
            "prefill_input_tokens": prefill_tokens,
            "prefill_wall_ms": decode_ms * 2,
            "decode_output_tokens": decode_tokens,
            "decode_wall_ms": decode_ms,
            "drafted_tokens": decode_tokens * 3,
            "accepted_draft_tokens": decode_tokens * 2,
        },
        "streamed_experts": {
            "decode": {
                "read": reads,
                "routed": routed,
                "read_bytes": reads * 1000,
                "loads": reads,
                "host_steps": {"work_ms": {"total": work_ms}},
            },
            "resident": resident,
            "slots": resident + 100,
            "chunks": 1,
            "cap_bytes": 3_000_000_000,
        },
        "memory_plan": {
            "budget": {
                "shared_prefill_bytes": 1_691_156_480,
                "kv_spill": {"hot_floor_bytes": 817_889_280},
            }
        },
        "memory_governor": {
            "host_available_bytes": 2_000_000_000,
            "growth_allowed": True,
        },
    }


class Option21ArmsTests(unittest.TestCase):
    def test_counters_flatten_the_status_fields_a_round_needs(self):
        counters = option21_arms.counters(snapshot(100, 20, 2000, 40, 100, 500, 1512))
        self.assertEqual(counters["decode_tokens"], 20)
        self.assertEqual(counters["requests_completed"], 20)
        self.assertEqual(counters["expert_reads"], 40)
        self.assertEqual(counters["resident_experts"], 1512)
        self.assertEqual(counters["hot_floor_bytes"], 817_889_280)
        self.assertIs(counters["growth_allowed"], True)

    def test_difference_diffs_counters_and_keeps_flags(self):
        before = option21_arms.counters(snapshot(100, 20, 2000, 40, 100, 500, 1512))
        after = option21_arms.counters(snapshot(1100, 536, 54000, 140, 300, 1500, 1786))
        delta = option21_arms.difference(before, after)
        self.assertEqual(delta["decode_tokens"], 516)
        self.assertEqual(delta["expert_reads"], 100)
        self.assertEqual(delta["resident_experts"], 274)
        self.assertIs(delta["growth_allowed"], True)
        self.assertEqual(delta["hot_floor_bytes"], 0)

    def test_probe_reads_the_timings_the_response_carries(self):
        original = option21_arms.chat
        option21_arms.chat = lambda url, model, prompt, max_tokens: {
            "seconds": 107.0,
            "payload": {
                "usage": {"prompt_tokens": 11362},
                "timings": {
                    "prompt_n": 11362,
                    "prompt_ms": 51850.0,
                    "predicted_n": 95,
                    "predicted_ms": 7760.0,
                    "cache_n": 0,
                },
                "metrics": {
                    "cache": {"matched_tokens": 0},
                    "speculation": {
                        "cycles": 25,
                        "drafted_tokens": 75,
                        "accepted_draft_tokens": 70,
                    },
                },
                "choices": [{"finish_reason": "length", "message": {"content": "ORCHID"}}],
            },
        }
        try:
            measured = option21_arms.probe("http://127.0.0.1:1235", None, "cold_8k", "records", 500, 96)
        finally:
            option21_arms.chat = original
        self.assertEqual(measured["prefill_ms"], 51850.0)
        self.assertEqual(measured["output_tokens"], 95)
        self.assertEqual(measured["cycles"], 25)
        self.assertEqual(measured["finish"], "length")

    def test_round_metrics_reads_decode_and_prefill_out_of_the_probes(self):
        probes = [
            {
                "probe": "cold_8k",
                "seconds": 107.0,
                "input_tokens": 11362,
                "cached_tokens": 0,
                "prefill_ms": 51850.0,
                "output_tokens": 96,
                "decode_ms": 9600.0,
                "cycles": 30,
                "drafted": 200,
                "accepted": 150,
            },
            {
                "probe": "decode_512",
                "seconds": 52.0,
                "input_tokens": 145,
                "cached_tokens": 128,
                "prefill_ms": 1000.0,
                "output_tokens": 512,
                "decode_ms": 51200.0,
                "cycles": 180,
                "drafted": 1000,
                "accepted": 800,
            },
            {
                "probe": "cached_8k",
                "seconds": 2.0,
                "input_tokens": 11362,
                "cached_tokens": 11328,
                "prefill_ms": 1920.0,
                "output_tokens": 96,
                "decode_ms": 9600.0,
                "cycles": 30,
                "drafted": 200,
                "accepted": 150,
            },
        ]
        round_delta = {
            "decode_tokens": 800,
            "expert_reads": 2000,
            "expert_routed": 5000,
            "expert_work_ms": 4000.0,
        }
        metrics = option21_arms.round_metrics(probes, round_delta)
        self.assertAlmostEqual(metrics["decode_ms_per_token"], 70400 / 704)
        self.assertAlmostEqual(metrics["decode_tokens_per_second"], 10.0)
        self.assertAlmostEqual(metrics["tokens_per_cycle"], 704 / 240)
        self.assertAlmostEqual(metrics["cold_prefill_seconds"], 51.85)
        self.assertAlmostEqual(metrics["cached_prefill_seconds"], 1.92)
        self.assertEqual(metrics["cached_prefill_tokens"], 11328)
        self.assertAlmostEqual(metrics["expert_work_ms_per_output_token"], 5.0)
        self.assertAlmostEqual(metrics["expert_hit_rate"], 0.6)
        self.assertAlmostEqual(metrics["draft_acceptance_rate"], 1100 / 1400)

    def test_engine_processes_finds_the_launcher_and_the_engine(self):
        listing = (
            "  12 bash ./startllamacpp.sh --direct 21\n"
            "  13 /Users/mymac/splash/splash/build/splash serve-native model.gguf\n"
            "  14 python3 dev/benchmarks/option21_arms.py\n"
        )
        self.assertEqual(option21_arms.engine_processes(listing), [12, 13])

    def test_answer_checks_catch_an_arm_that_trades_correctness_for_speed(self):
        checks = option21_arms.answer_checks([
            {"probe": "cold_8k", "content": "The final code is ORCHID."},
            {"probe": "decode_512", "content": "def merge_intervals(intervals): ..."},
            {"probe": "cached_8k", "content": "ORCHID"},
        ])
        self.assertEqual(checks, {"cold_final_code": True, "cached_final_code": True, "decode_returns_code": True})
        broken = option21_arms.answer_checks([{"probe": "cold_8k", "content": "I do not know."}])
        self.assertFalse(broken["cold_final_code"])

    def test_verdict_compares_each_metric_abba(self):
        def row(arm, decode_ms_per_token):
            return {
                "arm": arm,
                "metrics": {metric: decode_ms_per_token for metric in option21_arms.LOWER_IS_BETTER},
                "answers": {"cold_final_code": True, "cached_final_code": True, "decode_returns_code": True},
            }

        rounds = [
            row("baseline", 70.0),
            row("chunk1024", 63.0),
            row("chunk1024", 63.5),
            row("baseline", 70.5),
        ]
        result = option21_arms.verdict(rounds, "chunk1024")
        self.assertIn("decode_ms_per_token", result)
        self.assertTrue(result["decode_ms_per_token"]["pass"])
        self.assertLess(result["decode_ms_per_token"]["regression"], 0)
        self.assertTrue(result["answers"]["baseline"])
        self.assertEqual(option21_arms.verdict(rounds[:3], "chunk1024"), {})

    def test_env_sets_only_the_arm_flags_and_the_scratch_paths(self):
        env = option21_arms.build_env("chunk1024", 1236, Path("/tmp/cache"), Path("/tmp/logs"))
        self.assertEqual(env["SPLASH_FLASH_NEXT_PREFILL_CHUNK_TOKENS"], "1024")
        self.assertEqual(env["LLAMA_PORT"], "1236")
        self.assertEqual(env["SPLASH_FLASH_NEXT_CACHE_DIR"], "/tmp/cache")
        self.assertNotIn("SPLASH_FLASH_NEXT_MAX_CONTEXT", env)

    def test_plan_reports_the_memory_an_arm_plans_for(self):
        row = {
            "prefill_chunk_tokens": 1024,
            "maximum_context_tokens": 65536,
            "status": {
                "shared_prefill_bytes": 845_578_240,
                "hot_floor_bytes": 817_889_280,
                "expert_cap_bytes": 3_786_043,
                "expert_slots": 1932,
                "resident_experts": 1932,
                "expert_chunks": 2,
                "host_available_bytes": 2_000_000_000,
            },
        }
        plan = option21_arms.plan(row)
        self.assertEqual(plan["prefill_chunk_tokens"], 1024)
        self.assertEqual(plan["expert_slots"], 1932)


if __name__ == "__main__":
    unittest.main()
