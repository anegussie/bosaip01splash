#!/usr/bin/env python3
"""Probe existing PTQ1_0 gate/up kernels while preserving the idle primary."""

import argparse
import subprocess
from pathlib import Path

if __package__:
    from .dflash2_tuning import ROOT, guard_primary, released_primary, stop
else:
    from dflash2_tuning import ROOT, guard_primary, released_primary, stop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=31)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("rounds must be positive")
    args.results.mkdir(parents=True, exist_ok=False)
    for trial in (1, 2):
        released_primary()
        path = args.results / f"gate-up-{trial}.log"
        with path.open("w") as log:
            process = subprocess.Popen(
                [
                    str(ROOT / "build/engine-tests/gguf-projection-benchmark"),
                    str(ROOT / "build/splash.metallib"),
                    "ptq10",
                    "17408",
                    "5120",
                    "gateup",
                    str(args.rounds),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                with guard_primary(process, True):
                    process.wait(timeout=600)
                    if process.returncode:
                        raise RuntimeError("kernel sweep failed: " + str(path))
            finally:
                stop(process)
        print("gate/up sweep", trial, "complete", flush=True)


if __name__ == "__main__":
    main()
