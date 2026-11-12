"""Summarize completed matched option-21 trials without changing raw evidence."""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPORT = OUT.parent / "qwen38-option21-readahead-performance-20261112.md"


def load(path):
    return json.loads(path.read_text())


def midpoint(values):
    return statistics.median(values)


def metric(row, key):
    if key == "ttft":
        return row["sse_ttft_seconds"]
    return row["timings"][key]


def vm_counter(snapshot, name):
    match = re.search(r"^" + name + r":\s+(\d+)", snapshot["vm_stat"]["stdout"], re.M)
    assert match, name
    return int(match.group(1))


def fmt(values, decimals=2):
    return f"{midpoint(values):.{decimals}f} ({min(values):.{decimals}f}-{max(values):.{decimals}f})"


def main():
    assert load(OUT / "complete.json")["complete"]
    assert load(OUT / "production-restored.json")["ready"]
    groups = {"Original": ["A1", "A2"], "Candidate": ["B1", "B2"]}
    contract = load(OUT / "contract.json")
    baseline_identity = load(OUT / "A1/ready.json")["identity"]
    for label in ("A1", "B1", "B2", "A2"):
        identity = load(OUT / label / "ready.json")["identity"]
        assert identity["kv"] == baseline_identity["kv"]
        assert (
            identity["cache"]["loaded_model_layout_sha256"]
            == baseline_identity["cache"]["loaded_model_layout_sha256"]
        )
        for size in contract["contexts"]:
            assert (
                load(OUT / label / f"prompt-{size}.json")["sha256"]
                == load(OUT / "A1" / f"prompt-{size}.json")["sha256"]
            )
    assert (
        load(OUT / "binaries/baseline/sha256.json")["splash.metallib"]
        == load(OUT / "binaries/candidate/sha256.json")["splash.metallib"]
    )
    table, comparison, arms = [], {}, {}
    for size in contract["contexts"]:
        by_engine = {}
        for engine, labels in groups.items():
            cold = [load(OUT / label / f"{size}-cold.json") for label in labels]
            cached = [load(OUT / label / f"{size}-reuse.json") for label in labels]
            assert all(r["correct"] for r in cold + cached)
            assert len({r["usage"]["prompt_tokens"] for r in cold + cached}) == 1
            entry = dict(
                engine=engine,
                prompt=cold[0]["usage"]["prompt_tokens"],
                pp=[metric(r, "prompt_per_second") for r in cold],
                tps=[metric(r, "predicted_per_second") for r in cold],
                ttft=[metric(r, "ttft") for r in cold],
                cached_tps=[metric(r, "predicted_per_second") for r in cached],
                cached_ttft=[metric(r, "ttft") for r in cached],
                output_tokens=[r["usage"]["completion_tokens"] for r in cold + cached],
            )
            table.append(entry)
            by_engine[engine] = entry
        comparison[size] = {
            key + "_percent": 100
            * (
                midpoint(by_engine["Candidate"][key])
                / midpoint(by_engine["Original"][key])
                - 1
            )
            for key in ("pp", "tps", "ttft", "cached_tps", "cached_ttft")
        }
    for label in ("A1", "B1", "B2", "A2", "native-baseline", "native-candidate"):
        directory = OUT / label
        result = load(directory / "results.json")
        assert result["complete"] and all(r["correct"] for r in result["rows"])
        before, after = (
            load(directory / "system-before.json"),
            load(directory / "system-after.json"),
        )
        statuses = [
            r[k] for r in result["rows"] for k in ("status_before", "status_after")
        ]
        samples = [s for r in result["rows"] for s in r["samples"]]
        stats = statuses[-1]["streamed_experts"]
        drafted = sum(r["timings"].get("draft_n", 0) for r in result["rows"])
        accepted = sum(r["timings"].get("draft_n_accepted", 0) for r in result["rows"])
        io = {
            phase: {
                key: sum(r["expert_io_delta"][phase][key] for r in result["rows"])
                for key in (
                    "read_bytes",
                    "ahead_read_bytes",
                    "ahead_used_bytes",
                    "host_step_work_seconds",
                )
            }
            for phase in ("prefill", "decode")
        }
        arms[label] = dict(
            swapout_pages=vm_counter(after, "Swapouts")
            - vm_counter(before, "Swapouts"),
            thermals=sorted({s["thermal_state"] for s in samples + statuses}),
            pressures=sorted({s["memory_pressure"] for s in samples + statuses}),
            minimum_host_headroom_bytes=min(
                s["memory_governor"]["host_headroom_bytes"] for s in statuses
            ),
            expert_slots=sorted({s["streamed_experts"]["slots"] for s in statuses}),
            peak_metal_bytes=max(s["memory_actual"]["peak_bytes"] for s in statuses),
            kv_spilled_pages=max(s["kv_spill"]["pages"]["spilled"] for s in statuses),
            plane_cache=stats["plane_cache"],
            prepared_payload_read_bytes=sum(
                r["status_after"]["streamed_experts"]["plane_cache"]["read_bytes"]
                - r["status_before"]["streamed_experts"]["plane_cache"]["read_bytes"]
                for r in result["rows"]
            ),
            accepted=accepted,
            drafted=drafted,
            acceptance_percent=100 * accepted / drafted if drafted else None,
            expert_io=io,
            all_correct=True,
            requests=len(result["rows"]),
        )
    summary = dict(contract=contract, rows=table, comparison=comparison, arms=arms)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Option 21 read-ahead performance comparison - 2026-11-12",
        "",
        "The candidate did not deliver a consistent prefill or decode improvement. All observed",
        "fresh-throughput ranges overlap. Keep the original production engine and prepared caching",
        "disabled by default; these results do not justify enabling the candidate for speed.",
        "That decision has been applied: the original engine remains live, prepared caching is off,",
        "and only the new read-ahead prototype edits were restored to their pre-experiment source.",
        "The launcher fix for retaining 2,048-token chunks with custom context/cache settings remains useful.",
        "",
        "Original and candidate binaries were frozen before the run. The primary comparison",
        "uses the same immutable, warmed prepared-expert cache in A1/B1/B2/A2 order.",
        "Each cell reports the median of two trials with its observed range.",
        "",
        "| Filled prompt | Engine | Fresh PP tok/s | Fresh decode TPS | Cold first token s | Cached decode TPS | Cached first token s |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table:
        lines.append(
            f"| {row['prompt']:,} | {row['engine']} | {fmt(row['pp'])} | {fmt(row['tps'])} | "
            f"{fmt(row['ttft'], 3)} | {fmt(row['cached_tps'])} | {fmt(row['cached_ttft'], 3)} |"
        )
    lines += [
        "",
        "## Candidate change relative to original",
        "",
        "| Content tokens | Fresh PP | Fresh decode TPS | Cold first token | Cached decode TPS | Cached first token |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for size, changes in comparison.items():
        values = [
            f"{changes[key + '_percent']:+.2f}%"
            for key in ("pp", "tps", "ttft", "cached_tps", "cached_ttft")
        ]
        lines.append(f"| {size:,} | " + " | ".join(values) + " |")
    lines += [
        "",
        "Higher throughput and lower latency are better. Two observations per engine/context",
        "show repeatability limits; these percentage differences are not statistical confidence bounds.",
        "",
        "## Default path controls",
        "",
        "The normal path, with prepared caching disabled, was checked once per engine at 8K.",
        "These are controls, not a repeated performance comparison.",
        "",
        "| Engine | Fresh PP tok/s | Fresh decode TPS | Cold first token s | Cached decode TPS | Cached first token s |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, label in (
        ("Original", "native-baseline"),
        ("Candidate", "native-candidate"),
    ):
        c, z = (
            load(OUT / label / "8192-cold.json"),
            load(OUT / label / "8192-reuse.json"),
        )
        lines.append(
            f"| {name} | {c['timings']['prompt_per_second']:.2f} | {c['timings']['predicted_per_second']:.2f} | "
            f"{c['sse_ttft_seconds']:.3f} | {z['timings']['predicted_per_second']:.2f} | {z['sse_ttft_seconds']:.3f} |"
        )
    lines += [
        "",
        "## Correctness, memory and conditions",
        "",
        "| Arm | Timed requests | Correct | New swap-out pages | Thermal states | Pressure | Expert slots | Draft acceptance |",
        "| --- | ---: | --- | ---: | --- | --- | --- | ---: |",
    ]
    for label, arm in arms.items():
        lines.append(
            f"| {label} | {arm['requests']} | Yes | {arm['swapout_pages']} | {', '.join(arm['thermals'])} | "
            f"{', '.join(arm['pressures'])} | {', '.join(map(str, arm['expert_slots']))} | {arm['acceptance_percent']:.2f}% |"
        )
    lines += [
        "",
        "## Expert I/O and host-step work",
        "",
        "Mean reported counters per seven-request arm, excluding warmup:",
        "",
        "| Engine | Native source reads GiB | Prepared payload reads GiB | Prefill host-step work s | Decode host-step work s |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for engine, labels in groups.items():
        native = (
            midpoint(
                [
                    sum(
                        arms[label]["expert_io"][phase]["read_bytes"]
                        for phase in ("prefill", "decode")
                    )
                    for label in labels
                ]
            )
            / 2**30
        )
        prepared = (
            midpoint([arms[label]["prepared_payload_read_bytes"] for label in labels])
            / 2**30
        )
        prefill_work = midpoint(
            [
                arms[label]["expert_io"]["prefill"]["host_step_work_seconds"]
                for label in labels
            ]
        )
        decode_work = midpoint(
            [
                arms[label]["expert_io"]["decode"]["host_step_work_seconds"]
                for label in labels
            ]
        )
        lines.append(
            f"| {engine} | {native:.2f} | {prepared:.2f} | {prefill_work:.3f} | {decode_work:.3f} |"
        )
    lines += [
        "",
        "The smoke gates verified fresh and reused-prefix requests, a restart restore of the",
        "persistent prefix, prepared-cache hits with zero new writes/errors/corruptions,",
        "and executable Python output on both engines before the timed matrix.",
        "Every recall/counting completion used 96 output tokens; code used a 192-token budget",
        "and was executed against assertions. Thinking was disabled, temperature 0, seed 1234.",
        "Automatic verification matches option 21's serving profile and can produce different",
        "greedy outputs between requests; executable/recall correctness is checked independently.",
        "",
        "Both engines used the Q2_0 target and the same BF16 DFlash2 draft, INT8 KV, BF16 state,",
        "131,072 server context, 10.8G cap, 2,048-token chunks, automatic expert memory,",
        "64M PLE, one active request, and isolated 3G persistent prefix caches on the 16 GiB M5.",
        "Requests were submitted sequentially. The test transport used its default concurrency",
        "cap rather than production's explicit cap of one; no overlapping inference was observed.",
        "The largest prompt actually filled was 16,396 tokens; this does not measure full 131K throughput.",
        "The prepared cache's exact existing footprint was its quota, preventing writes and eviction.",
        "Cold means zero reused prefix tokens, with model/OS caches already warm. All timed",
        "requests started at nominal thermals; sampled states and memory pressure appear above.",
        "All 34 timed requests passed, with no new macOS swap-outs and no KV spill. Peak Metal",
        f"allocation was {max(a['peak_metal_bytes'] for a in arms.values()) / 2**30:.3f} GiB.",
        "Host pressure changed expert residency during some shorter requests in B2 and A2; every",
        "16K cold request used 1,512 slots. This limits attribution of the small throughput differences.",
        "The frozen cache holds 372 of 24,576 experts (about 1.5%); these results apply to that",
        "bounded cache and do not establish the behavior of a larger prepared-expert working set.",
        "The benchmark's temporary prefix caches were removed only after their servers stopped;",
        "the user's production prefix cache and model files were preserved.",
        "",
        "The original service was restored on port 1235 with matching model/build identity,",
        "context and chunk settings. No production binary was replaced.",
        "",
        "## Evidence",
        "",
        f"[Raw results, requests, responses, status, system snapshots and reproduction scripts]({OUT.name}/).",
        "`contract.json` records the workload, `binaries/*/sha256.json` pins both builds,",
        "and each arm's `ready.json` records the loaded model/build identity and memory plan.",
        "`frozen-cache-manifest.json` pins cache entries; its content was checked after every arm.",
        "`summary.json` includes I/O and host-step work deltas, draft acceptance, KV spill and memory.",
        "I/O deltas can include forecasts crossing request boundaries. Host-step work does not",
        "separately identify CPU execution, SSD waits or the fused GPU critical path. Native source",
        "bytes already include native read-ahead; prepared payload bytes have separate counters.",
        "The power snapshot records AC power and Low Power Mode disabled.",
        "`production-restored.json` records final service readiness.",
        "The large executables, Metal libraries and prepared-cache payloads are retained locally",
        "and excluded from Git; their manifests are versioned. The runner requires the original",
        "cache-enabled experimental wrapper and archived artifacts, as explained in the raw README.",
        "",
    ]
    REPORT.write_text("\n".join(lines))
    print(REPORT)
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
