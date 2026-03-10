#!/usr/bin/env python3
"""
v3: Competitive intelligence from Meta Ad Library.

Export competitor ads from facebook.com/ads/library (Princeton Review, Kaplan,
Khan Academy, Chegg, etc.), save to a JSON file, then run this script to
extract patterns (hooks, CTAs, tone angles) and save to output/competitor_insights.json.
The pipeline uses these insights when generating ads (see ad_engine.competitor.insights).

Usage:
  python scripts/run_competitive_intel.py path/to/competitor_ads.json
  python scripts/run_competitive_intel.py path/to/ads.json --output output/competitor_insights.json

Input JSON: array of ad objects. Each ad can have primary_text, headline, description, cta,
or any structure the LLM can interpret (e.g. {"copy": "..."} or {"text": "..."}).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ad_engine.competitor.insights import extract_patterns, save_insights


def main():
    parser = argparse.ArgumentParser(
        description="Extract competitor ad patterns (v3: Meta Ad Library competitive intelligence)"
    )
    parser.add_argument(
        "ads_json",
        type=str,
        help="Path to JSON file of competitor ads (from Meta Ad Library export or manual paste)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/competitor_insights.json",
        help="Output path for insights JSON (default: output/competitor_insights.json)",
    )
    args = parser.parse_args()

    path = Path(args.ads_json)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        print("Export ads from facebook.com/ads/library (e.g. Princeton Review, Kaplan, Chegg), save as JSON.", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)
    ads = data if isinstance(data, list) else [data]
    if not ads:
        print("No ads in file.", file=sys.stderr)
        sys.exit(1)

    insights = extract_patterns(ads)
    out_path = Path(args.output)
    save_insights(insights, out_path)
    print(f"Saved insights to {out_path}")
    print(f"  Hooks: {len(insights.get('hooks', []))}")
    print(f"  CTAs: {len(insights.get('ctas', []))}")
    print(f"  Tone angles: {len(insights.get('tone_angles', []))}")


if __name__ == "__main__":
    main()
