#!/usr/bin/env python3
"""Compare coding sampling policies on an already-running option-14 server."""

import argparse
import ast
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TASKS = {
    "review_intervals": (
        "Review this merge_intervals implementation. Explain the correctness bugs, their triggers, "
        "and fixes, then provide corrected Python code. Discuss input mutation, nested intervals, "
        "and intervals that touch at an endpoint.\n\n"
        "def merge_intervals(intervals):\n"
        "    intervals.sort()\n"
        "    merged = []\n"
        "    for start, end in intervals:\n"
        "        if merged and start < merged[-1][1]:\n"
        "            merged[-1][1] = end\n"
        "        else:\n"
        "            merged.append([start, end])\n"
        "    return merged\n",
        [],
    ),
    "merge_intervals": (
        "Implement merge_intervals(intervals). Input is a list of [start, end] integer pairs. "
        "Return sorted merged intervals as lists; merge overlapping or touching endpoints. "
        "Handle empty input and do not mutate the input. Use no imports.",
        [
            ([], []),
            ([[5, 7], [1, 3], [3, 6]], [[1, 7]]),
            ([[8, 10], [1, 2], [4, 5]], [[1, 2], [4, 5], [8, 10]]),
            ([[1, 8], [2, 3], [8, 9]], [[1, 9]]),
        ],
    ),
    "stable_unique": (
        "Implement stable_unique(items). Return a new list with duplicates removed, preserving "
        "first occurrence order. Support unhashable lists and dictionaries as elements, using "
        "equality rather than hashing. Handle empty input and do not mutate input. Use no imports.",
        [
            ([], []),
            ([3, 1, 3, 2, 1], [3, 1, 2]),
            ([[1], [2], [1]], [[1], [2]]),
            ([{"a": 1}, {"a": 1}, {"b": 2}], [{"a": 1}, {"b": 2}]),
        ],
    ),
    "chunked": (
        "Implement chunked(items, size). Return a list of list chunks with at most size elements; "
        "the final chunk may be smaller. Raise ValueError when size <= 0, including empty input. "
        "Handle empty input and do not mutate input. Use no imports.",
        [
            (([], 2), []),
            (([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]),
            (([1, 2], 5), [[1, 2]]),
            (([1, 2], 1), [[1], [2]]),
        ],
    ),
}


def check_code(task, text):
    if task == "review_intervals":
        for term in ("nested", "mutat", "touch"):
            assert term in text.lower(), f"review omitted {term}"
        return
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    code = match[1] if match else text
    tree = ast.parse(code)
    if not all(isinstance(node, ast.FunctionDef) for node in tree.body):
        raise ValueError("only function definitions are permitted")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise ValueError("unsupported code construct")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("private names are forbidden")
        if isinstance(node, ast.Attribute) and node.attr not in {
            "append",
            "extend",
            "copy",
            "sort",
            "get",
            "items",
            "keys",
            "values",
        }:
            raise ValueError("unsupported attribute")
    scope = {
        "__builtins__": {
            name: value
            for name, value in {
                "len": len,
                "range": range,
                "sorted": sorted,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "min": min,
                "max": max,
                "enumerate": enumerate,
                "zip": zip,
                "isinstance": isinstance,
                "int": int,
                "str": str,
                "any": any,
                "all": all,
                "sum": sum,
                "abs": abs,
                "bool": bool,
                "ValueError": ValueError,
            }.items()
        }
    }
    exec(compile(tree, "<coding-smoke>", "exec"), scope)
    function = scope[task]
    for inputs, expected in TASKS[task][1]:
        before = json.dumps(inputs, sort_keys=True)
        actual = function(*inputs) if task == "chunked" else function(inputs)
        assert actual == expected, (actual, expected)
        assert json.dumps(inputs, sort_keys=True) == before, "input was mutated"
    if task == "chunked":
        for size in (0, -1):
            try:
                function([], size)
            except ValueError:
                continue
            raise AssertionError("invalid chunk size was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:1235")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--check", choices=TASKS)
    parser.add_argument("--tasks", default="merge_intervals,stable_unique,chunked")
    parser.add_argument("--order", default="0.7,0,0,0.7")
    args = parser.parse_args()
    if args.check:
        check_code(args.check, sys.stdin.read())
        return
    if args.results is None:
        parser.error("--results is required")
    tasks = args.tasks.split(",")
    if not all(task in TASKS for task in tasks):
        parser.error("unknown task")
    order = [float(value) for value in args.order.split(",")]
    if not order or not all(0 <= value <= 2 for value in order):
        parser.error("temperatures must be in [0, 2]")

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        with urllib.request.urlopen(
            urllib.request.Request(
                args.url + path, data, {"Content-Type": "application/json"}
            ),
            timeout=240,
        ) as response:
            return json.load(response)

    context = "Repository notes for this synthetic coding test:\n" + "\n".join(
        f"Module utility_{i}: pure Python helpers; callers own their input data; stable ordering is required."
        for i in range(160)
    )
    results = {
        "before": request("/status"),
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": 384,
        "order": order,
        "runs": [],
    }
    try:
        for task, (instruction, _) in TASKS.items():
            if task not in tasks:
                continue
            for trial, temperature in enumerate(results["order"]):
                before = request("/status")
                started = time.monotonic()
                response = request(
                    "/v1/chat/completions",
                    {
                        "model": "bonsai-27b-splash",
                        "temperature": temperature,
                        "top_p": 0.8,
                        "top_k": 20,
                        "seed": 42,
                        "reasoning_effort": "none",
                        "max_tokens": 384,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You review Python code carefully and explain concrete bugs and fixes."
                                if task == "review_intervals"
                                else "You implement correct Python utilities. Return only the requested function's code, without commentary.",
                            },
                            {
                                "role": "user",
                                "content": context + "\n\nTask:\n" + instruction,
                            },
                        ],
                    },
                )
                elapsed = time.monotonic() - started
                after = request("/status")
                text = response["choices"][0]["message"]["content"]
                try:
                    check = subprocess.run(
                        [sys.executable, __file__, "--check", task],
                        input=text,
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    correct, error = check.returncode == 0, check.stderr[-1200:]
                except subprocess.TimeoutExpired:
                    correct, error = (
                        False,
                        "generated function exceeded the checker time limit",
                    )
                delta = {
                    key: after["metrics"][key] - before["metrics"][key]
                    for key in [
                        "drafted_tokens",
                        "accepted_draft_tokens",
                        "decode_output_tokens",
                        "decode_wall_ms",
                    ]
                }
                submitted = (
                    after["requests"]["submitted"] - before["requests"]["submitted"]
                )
                idle_before = (
                    before["requests"]["submitted"] == before["requests"]["completed"]
                )
                completed = (
                    after["requests"]["completed"] - before["requests"]["completed"]
                )
                run = {
                    "task": task,
                    "trial": trial,
                    "temperature": temperature,
                    "seconds": elapsed,
                    "response": response,
                    "correct": correct,
                    "check_error": error,
                    "metrics_delta": delta,
                    "isolated": submitted == 1 and completed == 1 and idle_before,
                    "before_requests": before["requests"],
                    "after_requests": after["requests"],
                    "draft_acceptance": delta["accepted_draft_tokens"]
                    / max(1, delta["drafted_tokens"]),
                }
                results["runs"].append(run)
                print(
                    task,
                    temperature,
                    "PASS" if correct else "FAIL",
                    "seconds",
                    round(elapsed, 2),
                    "decode_tps",
                    round(response["timings"]["predicted_per_second"], 2),
                    "acceptance",
                    round(run["draft_acceptance"], 3),
                    "isolated",
                    run["isolated"],
                    flush=True,
                )
                assert (
                    after["metal"]["healthy"]
                    and after["requests"]["failed"] == before["requests"]["failed"]
                ), after["requests"]
    finally:
        results["after"] = request("/status")
        args.results.parent.mkdir(parents=True, exist_ok=True)
        args.results.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
