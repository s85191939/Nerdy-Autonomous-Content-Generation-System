"""CLI: run pipeline, export reports."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from ad_engine.generate import AdGenerator
from ad_engine.generate.briefs import get_briefs_for_count
from ad_engine.evaluate import Evaluator
from ad_engine.iterate import IterationEngine
from ad_engine.storage import AdLibrary
from ad_engine.metrics.performance_metrics import PerformanceMetrics
from ad_engine.metrics.token_tracker import TokenTracker
from ad_engine.creative import ImageGenerator
from ad_engine.output.export_reports import export_ads_dataset, export_evaluation_report, export_evaluation_summary
from ad_engine.output.visualization import plot_iteration_quality
from ad_engine.config import QUALITY_THRESHOLD, MAX_ITERATIONS, FALLBACK_AD
from ad_engine.evaluate.dimension_scorer import default_evaluation

logger = logging.getLogger(__name__)


def _infer_backend() -> str:
    if (os.environ.get("OPENROUTER_API_KEY") or "").strip():
        return "openrouter"
    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        return "openai"
    return "gemini"


def run_pipeline(
    num_ads: int,
    max_iterations: int,
    output_dir: str,
    seed: int = 42,
    progress_callback=None,
):
    """Run the full generate→evaluate→iterate pipeline.
    Optional progress_callback(current, total, message, completed_ad=None).
    When an ad finishes, completed_ad is a dict: id, ad_copy, overall_score, accepted, iteration_count.
    Never raises; on fatal error returns a minimal result so caller never gets "no result".
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _minimal_result(accepted=0, avg_score=0.0, total_tokens=0, cost_usd=0.0, roi_1k=None, roi_dollar=None):
        return {
            "num_ads": num_ads,
            "accepted": accepted,
            "avg_score": round(avg_score, 2),
            "output_dir": str(out_dir),
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost_usd,
            "roi_accepted_per_1k_tokens": roi_1k,
            "roi_score_per_dollar": roi_dollar,
        }

    try:
        return _run_pipeline_body(
            num_ads, max_iterations, out_dir, seed, progress_callback, _minimal_result
        )
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        return _minimal_result()


def _run_pipeline_body(num_ads, max_iterations, out_dir, seed, progress_callback, _minimal_result):
    """Execute pipeline; may raise. Caller uses _minimal_result on exception."""
    backend = _infer_backend()
    token_tracker = TokenTracker(backend=backend)
    generator = AdGenerator(seed=seed, token_tracker=token_tracker)
    evaluator = Evaluator(seed=seed, token_tracker=token_tracker)
    engine = IterationEngine(
        generator=generator,
        evaluator=evaluator,
        quality_threshold=QUALITY_THRESHOLD,
        max_iterations=max_iterations,
    )
    library = AdLibrary(base_path=out_dir)
    metrics = PerformanceMetrics()

    briefs = get_briefs_for_count(num_ads, seed=seed)
    image_generator = ImageGenerator(use_placeholder_on_failure=False)
    results = []
    for i, brief in enumerate(briefs):
        ad_id = f"ad_{i}"
        if progress_callback:
            progress_callback(i + 1, num_ads, f"Processing ad {i + 1}/{num_ads} ...", completed_ad=None)
        elif (i + 1) % 10 == 0 or i == 0:
            print(f"Processing ad {i + 1}/{num_ads} ...", file=sys.stderr)
        try:
            result = engine.run_for_brief(brief)
            # Optional: generate image for v2 creatives; never fail the ad on image failure
            try:
                img_path = image_generator.generate(brief, result["ad"], out_dir, ad_id)
                if img_path is not None:
                    result["ad"] = dict(result["ad"])
                    result["ad"]["image_path"] = str(img_path.relative_to(out_dir))
            except Exception as img_err:
                logger.debug("Image generation skipped for %s: %s", ad_id, img_err)
            results.append(result)
        except Exception as e:
            logger.warning("Pipeline step failed for ad %s: %s. Using fallback result.", ad_id, e)
            fallback_eval = default_evaluation(5.0)
            results.append({
                "brief": brief,
                "ad": dict(FALLBACK_AD),
                "evaluation": fallback_eval,
                "iteration_count": 0,
                "accepted": False,
                "history": [{"iteration": 1, "ad": dict(FALLBACK_AD), "evaluation": fallback_eval}],
            })
            result = results[-1]
        ev = result["evaluation"]
        if progress_callback:
            progress_callback(
                i + 1,
                num_ads,
                f"Ad {i + 1}/{num_ads} done (score {ev['overall_score']})",
                completed_ad={
                    "id": ad_id,
                    "ad_copy": result["ad"],
                    "overall_score": ev["overall_score"],
                    "accepted": result["accepted"],
                    "iteration_count": result["iteration_count"],
                },
            )
        if result["accepted"]:
            library.add(
                ad_id=ad_id,
                brief=brief,
                ad_copy=result["ad"],
                scores=ev["scores"],
                overall_score=ev["overall_score"],
                iteration_count=result["iteration_count"],
            )
        try:
            for dim, data in ev["dimensions"].items():
                library.log_evaluation(ad_id, dim, data["score"], data.get("rationale", ""))
        except Exception as e:
            logger.warning("log_evaluation failed for %s: %s", ad_id, e)

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
    accepted_count = sum(1 for r in results if r["accepted"])
    cost_usd = token_tracker.estimated_cost_usd()
    metrics.record_run(cycle=1, avg_score=avg_score, token_cost=cost_usd, num_ads=len(results))
    library.save(prefix="ad_library")

    try:
        export_ads_dataset(export_ads, out_dir / "ads_dataset.json")
        export_evaluation_report(export_ads, out_dir / "evaluation_report.csv")
        export_evaluation_summary(export_ads, out_dir / "evaluation_summary.txt", quality_threshold=QUALITY_THRESHOLD)
        plot_iteration_quality(metrics.runs, out_dir / "iteration_quality_chart.png")
    except Exception as export_err:
        logger.warning("Export or visualization failed (run result still valid): %s", export_err)

    # Persist run for ROI dashboard
    run_record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "num_ads": num_ads,
        "accepted": accepted_count,
        "avg_score": round(avg_score, 2),
        "total_input_tokens": token_tracker.input_tokens,
        "total_output_tokens": token_tracker.output_tokens,
        "total_tokens": token_tracker.total_tokens,
        "estimated_cost_usd": cost_usd,
        "backend": backend,
        "roi_accepted_per_1k_tokens": token_tracker.roi_accepted_per_1k_tokens(accepted_count),
        "roi_score_per_dollar": token_tracker.roi_score_per_dollar(avg_score),
    }
    try:
        _append_run_history(out_dir, run_record)
    except Exception as hist_err:
        logger.warning("Could not append run history: %s", hist_err)

    return _minimal_result(
        accepted=accepted_count,
        avg_score=avg_score,
        total_tokens=token_tracker.total_tokens,
        cost_usd=cost_usd,
        roi_1k=run_record["roi_accepted_per_1k_tokens"],
        roi_dollar=run_record["roi_score_per_dollar"],
    )


def _append_run_history(out_dir: Path, run_record: dict) -> None:
    """Append a run to output/run_history.json for dashboard."""
    path = out_dir / "run_history.json"
    history = []
    if path.exists():
        try:
            with open(path) as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []
    if not isinstance(history, list):
        history = []
    history.append(run_record)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


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
