#!/usr/bin/env python3
"""
Calibrate the evaluator against reference ads (good/bad) before generating at scale.
Run this with reference ads from the Gauntlet/Nerdy Slack channel; adjust
examples/reference_ads_sample.json or pass your own JSON path.

Excellent rubric: "Calibrated against best/worst reference ads (provided via Slack)."
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ad_engine.evaluate import Evaluator


def main():
    parser = argparse.ArgumentParser(description="Calibrate evaluator on reference ads")
    parser.add_argument(
        "reference_ads",
        nargs="?",
        default="examples/reference_ads_sample.json",
        help="Path to JSON array of {id, expected_tier, ad_copy}",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    path = Path(args.reference_ads)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        print("Create it from reference ads in Gauntlet/Nerdy Slack, or use examples/reference_ads_sample.json", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        refs = json.load(f)

    evaluator = Evaluator(seed=args.seed)
    print("Calibration: running evaluator on reference ads\n")
    ok = True
    for ref in refs:
        ad = ref.get("ad_copy", ref)
        expected = ref.get("expected_tier", "unknown")
        rid = ref.get("id", "?")
        try:
            result = evaluator.evaluate(ad)
            score = result["overall_score"]
            conf = result.get("confidence", "N/A")
            print(f"  {rid} (expected: {expected}): score={score:.2f}, confidence={conf}")
            for dim, data in result["dimensions"].items():
                print(f"    {dim}: {data['score']} — {data.get('rationale', '')[:60]}...")
            if expected == "good" and score < 7.0:
                print(f"    WARNING: good reference scored below 7.0")
                ok = False
            if expected == "bad" and score >= 7.0:
                print(f"    WARNING: bad reference scored >= 7.0")
                ok = False
        except Exception as e:
            print(f"  {rid}: ERROR — {e}", file=sys.stderr)
            ok = False
        print()

    if ok:
        print("Calibration OK. Proceed with generation.")
    else:
        print("Calibration issues: adjust evaluator prompts or add more reference ads.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
