#!/usr/bin/env python3
"""Run a single world with no web server — useful for testing or batch
experiments. Prints periodic statistics to stdout.

    python run_headless.py --steps 5000 --pop 150 --seed 42
"""

from __future__ import annotations

import argparse
import time

from monkeyverse.config import SimConfig
from monkeyverse.simulation import Simulation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--pop", type=int, default=120)
    ap.add_argument("--width", type=int, default=128)
    ap.add_argument("--height", type=int, default=96)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--every", type=int, default=200)
    args = ap.parse_args()

    cfg = SimConfig(initial_population=args.pop, width=args.width,
                    height=args.height, seed=args.seed)
    sim = Simulation("headless", cfg, persistence=None)
    print(f"seed={sim.seed}  brain in/out = {sim.n_in}/{sim.n_out}")

    t0 = time.perf_counter()
    for i in range(args.steps):
        sim.step()
        if (i + 1) % args.every == 0:
            s = sim.stats_row()
            print(f"t={s['tick']:>6}  pop={s['population']:>4}  "
                  f"gen_max={s['max_generation']:>3}  "
                  f"E={s['avg_energy']:>6.1f}  signal={s['signal_activity']:.4f}  "
                  f"event={s['event']}")
            if s["population"] == 0:
                print("  (extinción)")
                break
    dt = time.perf_counter() - t0
    print(f"done: {args.steps} steps in {dt:.1f}s = {args.steps/dt:.0f} steps/s")


if __name__ == "__main__":
    main()
