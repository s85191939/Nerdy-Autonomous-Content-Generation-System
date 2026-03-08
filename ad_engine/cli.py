"""CLI: run pipeline, export reports."""

import argparse
import json
import sys
from pathlib import Path

from ad_engine.generate import AdGenerator
from ad_engine.generate.briefs import get_briefs_for_count
from ad_engine.evaluate import Evaluator
from ad_engine.iterate import IterationEngine
from ad_engine.storage import AdLibrary
from ad_engine.metrics.performance_metrics import PerformanceMetrics
from ad_engine.output.export_reports import export_ads_dataset, export_evaluation_report, export_evaluation_summary
from ad_engine.output.visualization import plot_iteration_quality
from ad_engine.config import QUALITY_THRESHOLD, MAX_ITERATIONS


def run_pipeline(
    num_ads: int,
    max_iterations: int,
    output_dir: str,
    seed: int = 42,
    progress_callback=None,
):
    """Run the full generate→evaluate→iterate pipeline. Optional progress_callback(current, total, message)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generator = AdGenerator(seed=seed)
    evaluator = Evaluator(seed=seed)
    engine = IterationEngine(
        generator=generator,
        evaluator=evaluator,
        quality_threshold=QUALITY_THRESHOLD,
        max_iterations=max_iterations,
    )
    library = AdLibrary(base_path=out_dir)
    metrics = PerformanceMetrics()

    briefs = get_briefs_for_count(num_ads, seed=seed)
    results = []
    for i, brief in enumerate(briefs):
        if progress_callback:
            progress_callback(i + 1, num_ads, f"Processing ad {i + 1}/{num_ads} ...")
        elif (i + 1) % 10 == 0 or i == 0:
            print(f"Processing ad {i + 1}/{num_ads} ...", file=sys.stderr)
        result = engine.run_for_brief(brief)
        results.append(result)
        ad_id = f"ad_{i}"
        ev = result["evaluation"]
        if result["accepted"]:
            library.add(
                ad_id=ad_id,
                brief=brief,
                ad_copy=result["ad"],
                scores=ev["scores"],
                overall_score=ev["overall_score"],
                iteration_count=result["iteration_count"],
            )
        for dim, data in ev["dimensions"].items():
            library.log_evaluation(ad_id, dim, data["score"], data.get("rationale", ""))

    # Build list for export (all generated, with scores and iteration history)
    export_ads = []
    for i, r in enumerate(results):
        history_export = []
        for j, h in enumerate(r.get("history", [])):
            ev = h.get("evaluation", {})
            scores = ev.get("scores", {})
            entry = {"iteration": h.get("iteration"), "overall_score": ev.get("overall_score"), "scores": dict(scores)}
            if j >= 1:
                prev_scores = r["history"][j - 1].get("evaluation", {}).get("scores", {})
                weak = min(prev_scores, key=lambda d: prev_scores.get(d, 10)) if prev_scores else None
                entry["targeted_dimension"] = weak
            history_export.append(entry)
        export_ads.append({
            "id": f"ad_{i}",
            "brief": r["brief"],
            "ad_copy": r["ad"],
            "scores": r["evaluation"]["scores"],
            "overall_score": r["evaluation"]["overall_score"],
            "iteration_count": r["iteration_count"],
            "accepted": r["accepted"],
            "iteration_history": history_export,
        })

    avg_score = sum(r["evaluation"]["overall_score"] for r in results) / len(results) if results else 0
    metrics.record_run(cycle=1, avg_score=avg_score, token_cost=0.0, num_ads=len(results))
    library.save(prefix="ad_library")

    export_ads_dataset(export_ads, out_dir / "ads_dataset.json")
    export_evaluation_report(export_ads, out_dir / "evaluation_report.csv")
    export_evaluation_summary(export_ads, out_dir / "evaluation_summary.txt", quality_threshold=QUALITY_THRESHOLD)
    plot_iteration_quality(metrics.runs, out_dir / "iteration_quality_chart.png")

    accepted_count = sum(1 for r in results if r["accepted"])
    return {
        "num_ads": num_ads,
        "accepted": accepted_count,
        "avg_score": round(avg_score, 2),
        "output_dir": str(out_dir),
    }


def run_cmd(args) -> None:
    result = run_pipeline(
        num_ads=max(1, args.num_ads),
        max_iterations=args.max_iterations,
        output_dir=args.output_dir,
        seed=args.seed,
    )
    print(
        f"Done. Generated {result['num_ads']} ads. Accepted (>= {QUALITY_THRESHOLD}): {result['accepted']}. Output: {result['output_dir']}",
        file=sys.stderr,
    )


def export_cmd(args) -> None:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    library = AdLibrary(base_path=out_dir)
    library.load(prefix="ad_library")
    ads = library.list_ads()
    if not ads:
        print("No ads in library. Run 'run' first.", file=sys.stderr)
        return
    export_ads_dataset(ads, out_dir / "ads_dataset.json")
    export_evaluation_report(ads, out_dir / "evaluation_report.csv")
    print(f"Exported to {out_dir}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nerdy Autonomous Ad Engine")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Generate and evaluate ads with iteration")
    run.add_argument("--num-ads", type=int, default=50, help="Number of ads to generate")
    run.add_argument("--max-iterations", type=int, default=MAX_ITERATIONS, help="Max iterations per ad")
    run.add_argument("--seed", type=int, default=42, help="Random seed")
    run.add_argument("--output-dir", type=str, default="output", help="Output directory")
    run.set_defaults(func=run_cmd)
    exp = sub.add_parser("export", help="Export reports from existing library")
    exp.add_argument("--output-dir", type=str, default="output", help="Output directory")
    exp.set_defaults(func=export_cmd)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
