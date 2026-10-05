"""Live regression checks for option 14 after integrating upstream fixes.

Start /Users/mymac/startllamacpp.sh --direct 14 first, then run this script.
Results include full responses and native status for workload verification.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:1235")
    parser.add_argument("--output", type=Path, default=Path("build/validation/option14-upstream.json"))
    args = parser.parse_args()
    results = {}

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        return urllib.request.urlopen(urllib.request.Request(
            args.base + path, data, {"Content-Type": "application/json"}), timeout=300)

    def status():
        with request("/status") as response:
            return json.load(response)

    common = {"model": "bonsai-27b-splash", "temperature": 0, "reasoning_effort": "none"}
    tool = {"type": "function", "function": {
        "name": "schedule_event",
        "description": "Schedule an event using the supplied start and reference code.",
        "parameters": {"type": "object", "properties": {
            "start": {"type": ["string", "number"]},
            "code": {"type": "string"},
        }, "required": ["start", "code"], "additionalProperties": False},
    }}
    try:
        deadline = time.monotonic() + 180
        while True:
            try:
                before = status()
                if before.get("ready"):
                    break
            except (urllib.error.URLError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("option 14 did not become ready within 180 seconds")
            time.sleep(1)
        results["status_before"] = before
        assert before["ready"] and before["metal"]["healthy"], before
        for stream in (False, True):
            body = {**common, "max_tokens": 256, "stream": stream, "tools": [tool],
                "tool_choice": {"type": "function", "function": {"name": "schedule_event"}},
                "messages": [{"role": "user", "content":
                    'Call schedule_event with start exactly "12:00" and code exactly "0800". Preserve both strings.'}]}
            started = time.monotonic()
            with request("/v1/chat/completions", body) as response:
                if not stream:
                    payload = json.load(response)
                    calls = payload["choices"][0]["message"]["tool_calls"]
                    function = calls[0]["function"]
                else:
                    payload, calls, finished = [], {}, False
                    for line in response:
                        if not line.startswith(b"data: "):
                            continue
                        data = line[6:].strip()
                        if data == b"[DONE]":
                            finished = True
                            break
                        event = json.loads(data)
                        assert "error" not in event, event
                        payload.append(event)
                        for choice in event.get("choices", []):
                            for call in choice["delta"].get("tool_calls", []):
                                function = calls.setdefault(call["index"], {"name": "", "arguments": ""})
                                for key, value in call.get("function", {}).items():
                                    function[key] += value
                    assert finished, "missing SSE completion"
                    function = calls[0]
                assert len(calls) == 1 and function["name"] == "schedule_event", calls
                values = json.loads(function["arguments"])
                assert values == {"start": "12:00", "code": "0800"}, values
                key = "tool_stream" if stream else "tool_complete"
                results[key] = {"seconds": time.monotonic() - started, "response": payload}
                print(key, "PASS", values, flush=True)

        # Explicit null follows reasoning effort; a non-boolean is rejected.
        with request("/v1/chat/completions", {**common, "max_tokens": 16,
            "chat_template_kwargs": {"enable_thinking": None},
            "messages": [{"role": "user", "content": "What is 2 + 2? Answer only the number."}]}) as response:
            result = json.load(response)
        message = result["choices"][0]["message"]
        assert "4" in message["content"] and not message.get("reasoning_content"), message
        results["thinking_null"] = result
        try:
            with request("/v1/chat/completions", {**common, "max_tokens": 16,
                "chat_template_kwargs": {"enable_thinking": 0},
                "messages": [{"role": "user", "content": "Hello"}]}):
                raise AssertionError("non-boolean enable_thinking was accepted")
        except urllib.error.HTTPError as error:
            assert error.code == 400, error.code
            results["thinking_invalid"] = json.load(error)
        prompt = "Read the records and remember the final code.\n" + "\n".join(
            f"Record {i}: the stored code is AMBER and the sequence number is {i}."
            for i in range(220)
        ) + "\nFinal record: the stored code is ORCHID. State the final code, then count from 1 to 100 separated by commas."
        for name in ("multi_chunk", "cached_repeat"):
            started = time.monotonic()
            with request("/v1/chat/completions", {**common, "max_tokens": 96,
                "messages": [{"role": "user", "content": prompt}]}) as response:
                result = json.load(response)
            assert "ORCHID" in result["choices"][0]["message"]["content"], result
            assert result["usage"]["prompt_tokens"] > 2048, result["usage"]
            results[name] = {"seconds": time.monotonic() - started,
                             "response": result, "status": status()}
            print(name, "PASS", result["usage"], flush=True)
        after = results["status_after"] = status()
        assert after["ready"] and after["metal"]["healthy"], after
        assert after["requests"]["failed"] == before["requests"]["failed"], after["requests"]
        results["passed"] = True
        print("Option 14 upstream regression smoke: PASS", flush=True)
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
