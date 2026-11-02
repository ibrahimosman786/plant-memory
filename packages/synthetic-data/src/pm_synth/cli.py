"""CLI: pm-synth generate --out ./out --seed 42"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path

from . import GENERATOR_VERSION
from .bundle import base_bundle
from .faults import FAULT_LIBRARY, VARIANTS
from .scenarios import build_scenarios
from .writers import write_bundle


def generate(out: Path, seed: int, only: list[str] | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for i, v in enumerate(VARIANTS):
        if only and v["id"] not in only:
            continue
        rnd = random.Random(seed * 1000 + i)
        b = base_bundle(v["id"], v["family"], v["template"], seed + i, v["units"])
        for fault in v["faults"]:
            FAULT_LIBRARY[fault](b)
        vdir = out / v["id"]
        regions = write_bundle(b, vdir, rnd)
        gold = {
            "generator_version": GENERATOR_VERSION,
            "variant": v,
            "plant": b.plant.to_dict(),
            "equipment_rows": b.equipment_rows,
            "io_rows": b.io_rows,
            "config_rows": [asdict(c) for c in b.config_rows],
            "datasheets": [asdict(d) for d in b.datasheets],
            "catalogue": [asdict(c) for c in b.catalogue],
            "rates": [asdict(r) for r in b.rates],
            "pid_regions": regions,
            "seeded_faults": [asdict(f) for f in b.faults],
        }
        (vdir / "ground_truth.json").write_text(json.dumps(gold, indent=2, default=str))
        index.append({"id": v["id"], "family": v["family"], "template": v["template"], "faults": v["faults"], "path": str(vdir.relative_to(out))})
    (out / "index.json").write_text(json.dumps({"generator_version": GENERATOR_VERSION, "seed": seed, "variants": index}, indent=2))
    (out / "scenarios.json").write_text(json.dumps(build_scenarios(), indent=2))
    print(f"generated {len(index)} variants and {len(build_scenarios())} scenarios under {out}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pm-synth")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--out", type=Path, default=Path("out"))
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--only", nargs="*", default=None)
    args = p.parse_args(argv)
    if args.cmd == "generate":
        generate(args.out, args.seed, args.only)


if __name__ == "__main__":
    main()
