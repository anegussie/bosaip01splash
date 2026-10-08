"""A small DFlash2 draft checkpoint, an independent byte-layout oracle of
every prepared image and their golden hashes."""

import argparse
import json
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dev.tests.fixture_files import (  # noqa: E402
    weight_file,
    write_safetensors,
)

F32 = struct.Struct("<f")


def f32(value):
    """value rounded once to float32: a float32 sum, difference or quotient
    computed in double and rounded once is the float32 operation's result."""
    return F32.unpack(F32.pack(value))[0]


def bf16(value):
    """The bits of the BF16 nearest a finite value, ties to even."""
    bits = struct.unpack("<I", F32.pack(value))[0]
    return (bits + 0x7FFF + ((bits >> 16) & 1)) >> 16


def half_away(value):
    """value rounded to an integer, halves away from zero."""
    return math.copysign(math.floor(abs(value) + 0.5), value)


def quantized_group(weights):
    """64 weights quantized to 4 bits as MLX's affine quantization rounds them
    (mlx.core.quantize, its Metal kernel, whose maximum starts at 0): the
    packed codes, and the scale and bias as BF16."""
    low, high = min(weights), max(0.0, *weights)
    low_edge = abs(low) > abs(high)
    scale = max(f32(f32(high - low) / 15), f32(1e-7))
    if not low_edge:
        scale = -scale
    edge = low if low_edge else high
    q0 = half_away(f32(edge / scale))
    bias = 0.0
    if q0 != 0:
        scale, bias = f32(edge / q0), edge
    codes = [
        int(min(max(half_away(f32(f32(w - bias) / scale)), 0), 15)) for w in weights
    ]
    packed = bytes(codes[i] | codes[i + 1] << 4 for i in range(0, len(codes), 2))
    return packed, struct.pack("<H", bf16(scale)), struct.pack("<H", bf16(bias))


def draft_fixture(root):
    """A two-layer DFlash2 checkpoint of width 256, its BF16 safetensors as
    its repository releases them, and the draft files its preparation must
    write: each projection quantized, every other tensor as stored."""
    tensors, values = {}, {}

    def add(name, shape, data=None):
        count = math.prod(shape)
        if data is None:
            # Multiples of 1/64 within 4 of zero, each exactly a BF16.
            seed = len(tensors) + 1
            data = [((i * 37 + seed * 11) % 509 - 254) / 64 for i in range(count)]
        values[name] = data
        tensors[name] = (shape, "BF16", struct.pack(f"<{count}H", *map(bf16, data)))
        return tensors[name][2]

    def quantized(names, columns):
        # The parts' rows quantized, each field in [rows / 256][groups][256]
        # tiles of its group bytes: codes, then scales, then biases.
        rows = [
            values[name][start : start + columns]
            for name in names
            for start in range(0, len(values[name]), columns)
        ]
        groups = columns // 64
        fields = [
            [quantized_group(row[g * 64 : (g + 1) * 64]) for g in range(groups)]
            for row in rows
        ]
        result = bytearray()
        for field in range(3):
            for tile in range(0, len(rows), 256):
                for group in range(groups):
                    for row in range(tile, tile + 256):
                        result += fields[row][group][field]
        return result

    def projection(name, rows, columns, data=None):
        add(name + ".weight", [rows, columns], data)
        return quantized([name + ".weight"], columns)

    expected = root / "expected"
    expected.mkdir()
    for layer in range(2):
        p = f"layers.{layer}."
        a = p + "self_attn."
        dynamic = None
        if layer == 0:
            # Two first rows of edge cases: all zero, where no scale puts 0 on
            # a code; constant; 0 to 15 with halves, which round away from
            # zero; a minimum farther from zero than the maximum; then groups
            # below zero, whose range still ends at 0: constant, spread, a
            # maximum near zero, and -15 to -1 with halves.
            dynamic = [0.0] * 64 + [0.75] * 64
            dynamic += [2.5, 8.5, *(float(i % 16) for i in range(62))]
            dynamic += [(i % 20) / 4 - 4 for i in range(64)]
            dynamic += [-0.75] * 64
            dynamic += [-(i % 16 + 1) / 4 for i in range(64)]
            dynamic += [-1 / 64, *(-(i % 32 + 1) / 8 for i in range(63))]
            dynamic += [-2.5, -8.5, *(-float(i % 15 + 1) for i in range(62))]
            dynamic += [((i * 37 + 11) % 509 - 254) / 64 for i in range(254 * 256)]
        sections = [
            add(p + "input_layernorm.weight", [256]),
            add(p + "attention_conv.base_kernel", [2, 2, 256]),
            projection(p + "attention_conv.kernel_projection", 256, 256, dynamic),
        ]
        for name, rows in (("q_proj", 128), ("k_proj", 64), ("v_proj", 64)):
            add(a + name + ".weight", [rows, 256])
        sections.append(
            quantized([a + n + ".weight" for n in ("q_proj", "k_proj", "v_proj")], 256)
        )
        sections += [
            add(a + "q_norm.weight", [64]),
            add(a + "k_norm.weight", [64]),
            projection(a + "o_proj", 256, 128),
            add(p + "post_attention_layernorm.weight", [256]),
            add(p + "mlp_conv.base_kernel", [2, 2, 256]),
            projection(p + "mlp_conv.kernel_projection", 256, 256),
            projection(p + "mlp.gate_proj", 256, 256),
            projection(p + "mlp.up_proj", 256, 256),
            projection(p + "mlp.down_proj", 256, 256),
        ]
        (expected / f"layer-{layer}.bin").write_bytes(
            weight_file("MDFD0004", layer, 0, sections)
        )
    sections = [
        projection("fc", 256, 256),
        add("hidden_norm.weight", [256]),
        add("norm.weight", [256]),
        projection("candidate_selector.hidden_projection", 256, 256),
        add("candidate_selector.predecessor_codebook", [256, 256]),
        add("candidate_selector.successor_codebook", [256, 256]),
    ]
    (expected / "model.bin").write_bytes(weight_file("MDFD0004", 2, 1, sections))
    write_safetensors(root / "model.safetensors", tensors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("metallib", type=Path)
    parser.add_argument("goldens", type=Path)
    args = parser.parse_args()
    golden = json.loads(args.goldens.read_text())["affine_images"]["draft"]
    with tempfile.TemporaryDirectory(prefix="splash-affine-preparation-") as directory:
        root = Path(directory)
        draft_fixture(root)
        command = [str(args.binary.resolve()), str(args.metallib.resolve()), str(root)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        hashes = {
            name: digest
            for marker, name, digest in (
                line.split()
                for line in result.stdout.splitlines()
                if line.startswith("prepared ")
            )
        }
        assert hashes == golden, hashes
        print(result.stdout.splitlines()[-1])


if __name__ == "__main__":
    main()
