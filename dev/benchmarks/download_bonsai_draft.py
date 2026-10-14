#!/usr/bin/env python3
"""Download a pinned Bonsai DFlash2 candidate into a benchmark directory."""

import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--revision", help="pin a published checkpoint commit")
    args = parser.parse_args()
    repo = "naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2"
    revision = HfApi().model_info(repo, revision=args.revision).sha
    args.directory.mkdir(parents=True, exist_ok=True)
    (args.directory / "provenance.json").write_text(
        json.dumps({"repo": repo, "revision": revision}, indent=2) + "\n"
    )
    print("Downloading", repo, revision, flush=True)
    root = snapshot_download(
        repo,
        revision=revision,
        local_dir=args.directory / "draft",
        allow_patterns=["config.json", "model.safetensors", "README.md"],
        max_workers=1,
    )
    print("Candidate directory:", root, flush=True)


if __name__ == "__main__":
    main()
