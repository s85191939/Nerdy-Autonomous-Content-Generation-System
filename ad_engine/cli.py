"""Pipeline functions for Nerdy Autonomous Ad Engine (web-only)."""

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
from ad_engine.creative.visual_evaluator import evaluate_visual
from ad_engine.output.export_reports import export_ads_dataset, export_evaluation_report, export_evaluation_summary
from ad_engine.output.visualization import plot_iteration_quality
from ad_engine.config import QUALITY_THRESHOLD, MAX_ITERATIONS, FALLBACK_AD, DIMENSION_WEIGHTS
from ad_engine.generate.prompt_templates import VARIANT_ANGLES, build_variant_angles
from ad_engine.evaluate.dimension_scorer import default_evaluation
from ad_engine.iterate.improvement_strategies import get_improvement_hint
from ad_engine.competitor.insights import load_insights

logger = logging.getLogger(__name__)


def _infer_backend() -> str:
    """Infer which backend will be used (same order as get_llm: Gemini -> OpenRouter -> OpenAI)."""
    if (os.environ.get("GEMINI_API_KEY") or "").strip():
        return "gemini"
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
    custom_brief: dict = None,
    quality_threshold: float = None,
    dimension_weights: dict = None,
    num_variants: int = 1,
    variant_angles: list = None,
    enable_image_gen: bool = False,
    concurrency: int = 1,
):
    """Run the full generate→evaluate→iterate pipeline.
    Optional progress_callback(current, total, message, completed_ad=None).
    When an ad finishes, completed_ad is a dict: id, ad_copy, overall_score, accepted, iteration_count.
    If custom_brief is provided (keys: audience, product, goal, tone), use it for all ads instead of default briefs.
    quality_threshold: override default 7.0. dimension_weights: optional override for dimension weights.
    num_variants: when >1, generate this many variants per brief (A/B style) with variant_angles or default angles.
    enable_image_gen: if True, generate an image per ad (v2) and run visual evaluation.
    concurrency: run up to this many ads in parallel (1 = sequential, 2–5 recommended for faster first results).
    Never raises; on fatal error returns a minimal result so caller never gets "no result".
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if quality_threshold is None:
        quality_threshold = QUALITY_THRESHOLD
    if dimension_weights is None:
        dimension_weights = DIMENSION_WEIGHTS
    if variant_angles is None or len(variant_angles) == 0:
        variant_angles = VARIANT_ANGLES

    def _minimal_result(accepted=0, avg_score=0.0, total_tokens=0, cost_usd=0.0, roi_1k=None, roi_dollar=None, backend=None):
        r = {
            "num_ads": num_ads,
            "accepted": accepted,
            "avg_score": round(avg_score, 2),
            "output_dir": str(out_dir),
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost_usd,
            "roi_accepted_per_1k_tokens": roi_1k,
            "roi_score_per_dollar": roi_dollar,
        }
        if backend is not None:
            r["backend"] = backend
        return r

    try:
        return _run_pipeline_body(
            num_ads, max_iterations, out_dir, seed, progress_callback, _minimal_result,
            custom_brief=custom_brief,
            quality_threshold=quality_threshold,
            dimension_weights=dimension_weights,
            num_variants=num_variants,
            variant_angles=variant_angles,
            enable_image_gen=enable_image_gen,
            concurrency=max(1, min(int(concurrency) if concurrency else 1, 8)),
        )
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        return _minimal_result()


def _run_pipeline_body(num_ads, max_iterations, out_dir, seed, progress_callback, _minimal_result, custom_brief=None, quality_threshold=None, dimension_weights=None, num_variants=1, variant_angles=None, enable_image_gen=False, concurrency=1):
    """Execute pipeline; may raise. Caller uses _minimal_result on exception."""
    if quality_threshold is None:
        quality_threshold = QUALITY_THRESHOLD
    if dimension_weights is None:
        dimension_weights = DIMENSION_WEIGHTS
    if variant_angles is None or len(variant_angles) == 0:
        variant_angles = VARIANT_ANGLES

    backend = _infer_backend()
    token_tracker = TokenTracker(backend=backend)
    generator = AdGenerator(seed=seed, token_tracker=token_tracker)
    evaluator = Evaluator(seed=seed, token_tracker=token_tracker, dimension_weights=dimension_weights)
    try:
        generator._reference_insights = load_insights(out_dir / "competitor_insights.json")
    except Exception:
        generator._reference_insights = None
    engine = IterationEngine(
        generator=generator,
        evaluator=evaluator,
        quality_threshold=quality_threshold,
        max_iterations=max_iterations,
    )
    library = AdLibrary(base_path=out_dir)
    metrics = PerformanceMetrics()

    if custom_brief and isinstance(custom_brief, dict):
        base_briefs = [dict(custom_brief) for _ in range(num_ads)]
    else:
        base_briefs = get_briefs_for_count(num_ads, seed=seed)

    tasks = []
    for i, brief in enumerate(base_briefs):
        if num_variants <= 1:
            tasks.append((brief, 0, ""))
        else:
            for v in range(num_variants):
                tasks.append((brief, v, f"_v{v}"))

    image_generator = ImageGenerator(use_placeholder_on_failure=True) if enable_image_gen else None
    results = [None] * len(tasks)  # preserve order for export

    # ── FAST BATCH PATH with auto-iteration ──
    # Generate N ads in one batch, evaluate all, then iterate any below threshold until they pass.
    MAX_IMPROVE_CYCLES = 10  # safety cap to prevent infinite loops
    use_batch = (not enable_image_gen and num_variants <= 1)
    if use_batch:
        if progress_callback:
            progress_callback(0, len(tasks), "Generating all ads in one batch...", completed_ad=None)
        try:
            briefs_list = [t[0] for t in tasks]
            ads = generator.generate_batch(briefs_list, count=len(tasks))
            if progress_callback:
                progress_callback(0, len(tasks), "Scoring all ads...", completed_ad=None)
            evals = evaluator.evaluate_batch(ads, brief=briefs_list[0])
            # Build initial results
            for idx in range(len(tasks)):
                brief = tasks[idx][0]
                ad = ads[idx] if idx < len(ads) else dict(FALLBACK_AD)
                ev = evals[idx] if idx < len(evals) else default_evaluation(5.0, dimension_weights)
                accepted = ev["overall_score"] >= quality_threshold
                ad_id = f"ad_{idx}"
                results[idx] = {
                    "brief": brief,
                    "ad": ad,
                    "evaluation": ev,
                    "iteration_count": 1,
                    "accepted": accepted,
                    "history": [{"iteration": 1, "ad": ad, "evaluation": ev}],
                    "_ad_id": ad_id,
                }
                if progress_callback:
                    progress_callback(idx + 1, len(tasks), f"Ad {idx + 1}/{len(tasks)} scored ({ev['overall_score']})", completed_ad={
                        "id": ad_id,
                        "ad_copy": ad,
                        "overall_score": ev["overall_score"],
                        "accepted": accepted,
                        "iteration_count": 1,
                    })

            # ── AUTO-ITERATE below-threshold ads until they all pass ──
            for cycle in range(MAX_IMPROVE_CYCLES):
                below = [(i, r) for i, r in enumerate(results) if r is not None and not r["accepted"]]
                if not below:
                    break  # all ads meet threshold
                if progress_callback:
                    progress_callback(
                        len(tasks) - len(below), len(tasks),
                        f"Improving {len(below)} ads below threshold (cycle {cycle + 2})...",
                        completed_ad=None,
                    )
                # Improve all below-threshold ads in parallel
                from concurrent.futures import ThreadPoolExecutor
                def _improve_one(item):
                    i, r = item
                    ad = r["ad"]
                    brief = r["brief"]
                    ev = r["evaluation"]
                    scores = ev.get("scores", {})
                    weak = min(scores, key=lambda d: scores.get(d, 10)) if scores else "clarity"
                    rationale = ev.get("dimensions", {}).get(weak, {}).get("rationale", "") or get_improvement_hint(weak, brief=brief)
                    new_ad = generator.improve(dict(ad), weak, rationale, brief=brief)
                    new_ev = evaluator.evaluate(new_ad, brief=brief)
                    return (i, new_ad, new_ev, weak)

                with ThreadPoolExecutor(max_workers=min(len(below), 8)) as executor:
                    futures = [executor.submit(_improve_one, item) for item in below]
                    for f in futures:
                        try:
                            i, new_ad, new_ev, weak = f.result()
                        except Exception as e:
                            logger.warning("Improve failed for ad %d: %s", i, e)
                            continue
                        r = results[i]
                        iter_num = r["iteration_count"] + 1
                        accepted = new_ev["overall_score"] >= quality_threshold
                        r["ad"] = new_ad
                        r["evaluation"] = new_ev
                        r["iteration_count"] = iter_num
                        r["accepted"] = accepted
                        r["history"].append({"iteration": iter_num, "ad": new_ad, "evaluation": new_ev})
                        if progress_callback:
                            progress_callback(
                                len(tasks) - len([(ii, rr) for ii, rr in enumerate(results) if rr and not rr["accepted"]]),
                                len(tasks),
                                f"Ad {i} improved: {new_ev['overall_score']} (was {r['history'][-2]['evaluation']['overall_score']}, targeted {weak})",
                                completed_ad={
                                    "id": r["_ad_id"],
                                    "ad_copy": new_ad,
                                    "overall_score": new_ev["overall_score"],
                                    "accepted": accepted,
                                    "iteration_count": iter_num,
                                },
                            )

            # Log to library
            for r in results:
                if r is None:
                    continue
                ev = r["evaluation"]
                try:
                    library.add(ad_id=r["_ad_id"], brief=r["brief"], ad_copy=r["ad"], scores=ev["scores"], overall_score=ev["overall_score"], iteration_count=r["iteration_count"])
                    for dim, data in ev["dimensions"].items():
                        library.log_evaluation(r["_ad_id"], dim, data["score"], data.get("rationale", ""))
                except Exception as e:
                    logger.warning("log_evaluation failed for %s: %s", r["_ad_id"], e)

        except Exception as batch_err:
            logger.warning("Batch path failed, falling back to per-ad: %s", batch_err)
            use_batch = False  # fall through to per-ad path

    # ── PER-AD PATH: used when image gen is enabled or batch failed ──
    if not use_batch:
        def _process_one(args):
            idx, (brief, variant_idx, variant_suffix) = args
            ad_id = f"ad_{idx}{variant_suffix}"
            creative_angle = variant_angles[variant_idx % len(variant_angles)] if num_variants > 1 else None
            try:
                result = engine.run_for_brief(brief, creative_angle=creative_angle)
                if image_generator is not None:
                    try:
                        img_path = image_generator.generate(brief, result["ad"], out_dir, ad_id)
                        if img_path is not None:
                            result["ad"] = dict(result["ad"])
                            result["ad"]["image_path"] = img_path.name
                            try:
                                visual_scores = evaluate_visual(brief, result["ad"], img_path, token_tracker)
                                if visual_scores:
                                    result["ad"]["visual_scores"] = visual_scores
                            except Exception as ve:
                                logger.debug("Visual evaluation skipped for %s: %s", ad_id, ve)
                    except Exception as img_err:
                        logger.debug("Image generation skipped for %s: %s", ad_id, img_err)
                if num_variants > 1:
                    result["ad"] = dict(result["ad"])
                    result["ad"]["variant_id"] = variant_idx
                    result["ad"]["variant_angle"] = (creative_angle[:50] + "...") if creative_angle and len(creative_angle) > 50 else creative_angle
                result["_ad_id"] = ad_id
                return (idx, result)
            except Exception as e:
                logger.warning("Pipeline step failed for ad %s: %s. Using fallback result.", ad_id, e)
                fallback_eval = default_evaluation(5.0)
                return (idx, {
                    "brief": brief,
                    "ad": dict(FALLBACK_AD),
                    "evaluation": fallback_eval,
                    "iteration_count": 0,
                    "accepted": False,
                    "history": [{"iteration": 1, "ad": dict(FALLBACK_AD), "evaluation": fallback_eval}],
                    "_ad_id": ad_id,
                })

        if concurrency <= 1:
            for idx, (brief, variant_idx, variant_suffix) in enumerate(tasks):
                if progress_callback:
                    progress_callback(idx + 1, len(tasks), f"Processing ad {idx + 1}/{len(tasks)} ...", completed_ad=None)
                elif (idx + 1) % 10 == 0 or idx == 0:
                    print(f"Processing ad {idx + 1}/{len(tasks)} ...", file=sys.stderr)
                _, result = _process_one((idx, (brief, variant_idx, variant_suffix)))
                results[idx] = result
                ev = result["evaluation"]
                if progress_callback:
                    progress_callback(idx + 1, len(tasks), f"Ad {idx + 1}/{len(tasks)} done (score {ev['overall_score']})", completed_ad={
                        "id": result["_ad_id"],
                        "ad_copy": result["ad"],
                        "overall_score": ev["overall_score"],
                        "accepted": result["accepted"],
                        "iteration_count": result["iteration_count"],
                    })
                if result["accepted"]:
                    library.add(ad_id=result["_ad_id"], brief=result["brief"], ad_copy=result["ad"], scores=ev["scores"], overall_score=ev["overall_score"], iteration_count=result["iteration_count"])
                try:
                    for dim, data in ev["dimensions"].items():
                        library.log_evaluation(result["_ad_id"], dim, data["score"], data.get("rationale", ""))
                except Exception as e:
                    logger.warning("log_evaluation failed for %s: %s", result["_ad_id"], e)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            completed_count = [0]
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                future_to_idx = {executor.submit(_process_one, (idx, (brief, variant_idx, variant_suffix))): idx for idx, (brief, variant_idx, variant_suffix) in enumerate(tasks)}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        _, result = future.result()
                    except Exception as e:
                        brief, variant_idx, variant_suffix = tasks[idx]
                        ad_id = f"ad_{idx}{variant_suffix}"
                        fallback_eval = default_evaluation(5.0)
                        result = {"brief": brief, "ad": dict(FALLBACK_AD), "evaluation": fallback_eval, "iteration_count": 0, "accepted": False, "history": [{"iteration": 1, "ad": dict(FALLBACK_AD), "evaluation": fallback_eval}], "_ad_id": ad_id}
                    results[idx] = result
                    ev = result["evaluation"]
                    completed_count[0] += 1
                    if progress_callback:
                        progress_callback(completed_count[0], len(tasks), f"Ad {completed_count[0]}/{len(tasks)} done (score {ev['overall_score']})", completed_ad={
                            "id": result["_ad_id"],
                            "ad_copy": result["ad"],
                            "overall_score": ev["overall_score"],
                            "accepted": result["accepted"],
                            "iteration_count": result["iteration_count"],
                        })
                    if result["accepted"]:
                        library.add(ad_id=result["_ad_id"], brief=result["brief"], ad_copy=result["ad"], scores=ev["scores"], overall_score=ev["overall_score"], iteration_count=result["iteration_count"])
                    try:
                        for dim, data in ev["dimensions"].items():
                            library.log_evaluation(result["_ad_id"], dim, data["score"], data.get("rationale", ""))
                    except Exception as e:
                        logger.warning("log_evaluation failed for %s: %s", result["_ad_id"], e)

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
            "id": r.get("_ad_id", f"ad_{i}"),
            "brief": r["brief"],
            "ad_copy": r["ad"],
            "scores": r["evaluation"]["scores"],
            "overall_score": r["evaluation"]["overall_score"],
            "confidence": r["evaluation"].get("confidence"),
            "dimensions": r["evaluation"].get("dimensions"),
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
        export_evaluation_summary(
            export_ads,
            out_dir / "evaluation_summary.txt",
            quality_threshold=quality_threshold,
            backend=backend,
            run_history_path=out_dir / "run_history.json",
        )
        plot_iteration_quality(metrics.runs, out_dir / "iteration_quality_chart.png")
    except Exception as export_err:
        logger.warning("Export or visualization failed (run result still valid): %s", export_err)

    # Persist run for ROI dashboard
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_record = {
        "run_id": run_id,
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
        # v3: self-healing — detect quality drop vs previous run before appending
        from ad_engine.metrics.self_heal import run_self_heal_checks
        run_self_heal_checks(avg_score, out_dir, run_id)
        _append_run_history(out_dir, run_record)
        runs_dir = out_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        export_ads_dataset(export_ads, run_dir / "ads_dataset.json")
        export_evaluation_report(export_ads, run_dir / "evaluation_report.csv")
        export_evaluation_summary(
            export_ads,
            run_dir / "evaluation_summary.txt",
            quality_threshold=quality_threshold,
            backend=backend,
            run_history_path=out_dir / "run_history.json",
        )
        chart_src = out_dir / "iteration_quality_chart.png"
        if chart_src.exists():
            import shutil
            shutil.copy2(chart_src, run_dir / "iteration_quality_chart.png")
    except Exception as hist_err:
        logger.warning("Could not append run history: %s", hist_err)

    result = _minimal_result(
        accepted=accepted_count,
        avg_score=avg_score,
        total_tokens=token_tracker.total_tokens,
        cost_usd=cost_usd,
        roi_1k=run_record["roi_accepted_per_1k_tokens"],
        roi_dollar=run_record["roi_score_per_dollar"],
        backend=backend,
    )
    result["run_id"] = run_id
    result["run_timestamp"] = run_record["timestamp"]
    result["quality_threshold"] = quality_threshold
    return result


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


def iterate_campaign(output_dir: str, run_id: str, max_extra_iterations: int = 3, seed: int = 42, progress_callback=None):
    """Re-run improve loop on every ad in campaign at output/runs/<run_id>/ads_dataset.json. Saves as new run with iterated_from."""
    out_dir = Path(output_dir)
    runs_dir = out_dir / "runs"
    ads_path = runs_dir / run_id / "ads_dataset.json"
    if not ads_path.exists():
        return {"run_id": None, "iterated_from": run_id, "num_ads": 0, "accepted": 0, "avg_score": 0.0, "output_dir": str(out_dir), "error": "Campaign data not found."}
    try:
        with open(ads_path) as f:
            existing_ads = json.load(f)
    except Exception as e:
        return {"run_id": None, "iterated_from": run_id, "num_ads": 0, "accepted": 0, "error": str(e)}
    if not isinstance(existing_ads, list) or not existing_ads:
        return {"run_id": None, "iterated_from": run_id, "num_ads": 0, "accepted": 0, "error": "No ads in campaign."}
    backend = _infer_backend()
    token_tracker = TokenTracker(backend=backend)
    generator = AdGenerator(seed=seed, token_tracker=token_tracker)
    evaluator = Evaluator(seed=seed, token_tracker=token_tracker)
    engine = IterationEngine(generator=generator, evaluator=evaluator, quality_threshold=QUALITY_THRESHOLD, max_iterations=max_extra_iterations)
    num_ads = len(existing_ads)
    results = []
    for i, item in enumerate(existing_ads):
        brief = item.get("brief") or {}
        ad_copy = item.get("ad_copy") or item
        ad_id = item.get("id", f"ad_{i}")
        if progress_callback:
            progress_callback(i + 1, num_ads, f"Re-iterating ad {i + 1}/{num_ads} ...", None)
        try:
            result = engine.run_from_ad(ad_copy, brief)
            results.append(result)
        except Exception as e:
            logger.warning("iterate_campaign ad %s failed: %s", ad_id, e)
            results.append({"brief": brief, "ad": dict(ad_copy), "evaluation": default_evaluation(5.0), "iteration_count": 0, "accepted": False, "history": []})
        if progress_callback and results:
            ev = results[-1]["evaluation"]
            progress_callback(i + 1, num_ads, f"Ad {i + 1}/{num_ads} done", {"id": ad_id, "ad_copy": results[-1]["ad"], "overall_score": ev["overall_score"], "accepted": results[-1]["accepted"], "iteration_count": results[-1]["iteration_count"]})
    export_ads = []
    for i, r in enumerate(results):
        history_export = []
        for j, h in enumerate(r.get("history", [])):
            ev = h.get("evaluation", {})
            entry = {"iteration": h.get("iteration"), "overall_score": ev.get("overall_score"), "scores": dict(ev.get("scores", {}))}
            if j >= 1 and r.get("history"):
                prev_scores = r["history"][j - 1].get("evaluation", {}).get("scores", {})
                entry["targeted_dimension"] = min(prev_scores, key=lambda d: prev_scores.get(d, 10)) if prev_scores else None
            history_export.append(entry)
        export_ads.append({"id": existing_ads[i].get("id", f"ad_{i}"), "brief": r["brief"], "ad_copy": r["ad"], "scores": r["evaluation"]["scores"], "overall_score": r["evaluation"]["overall_score"], "confidence": r["evaluation"].get("confidence"), "dimensions": r["evaluation"].get("dimensions"), "iteration_count": r["iteration_count"], "accepted": r["accepted"], "iteration_history": history_export})
    avg_score = sum(r["evaluation"]["overall_score"] for r in results) / len(results) if results else 0
    accepted_count = sum(1 for r in results if r["accepted"])
    cost_usd = token_tracker.estimated_cost_usd()
    new_run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_record = {"run_id": new_run_id, "timestamp": datetime.utcnow().isoformat() + "Z", "iterated_from": run_id, "num_ads": num_ads, "accepted": accepted_count, "avg_score": round(avg_score, 2), "total_input_tokens": token_tracker.input_tokens, "total_output_tokens": token_tracker.output_tokens, "total_tokens": token_tracker.total_tokens, "estimated_cost_usd": cost_usd, "backend": backend, "roi_accepted_per_1k_tokens": token_tracker.roi_accepted_per_1k_tokens(accepted_count), "roi_score_per_dollar": token_tracker.roi_score_per_dollar(avg_score)}
    try:
        _append_run_history(out_dir, run_record)
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / new_run_id).mkdir(parents=True, exist_ok=True)
        export_ads_dataset(export_ads, runs_dir / new_run_id / "ads_dataset.json")
    except Exception as hist_err:
        logger.warning("Could not save iterated campaign: %s", hist_err)
    return {"run_id": new_run_id, "iterated_from": run_id, "num_ads": num_ads, "accepted": accepted_count, "avg_score": round(avg_score, 2), "output_dir": str(out_dir), "total_tokens": token_tracker.total_tokens, "estimated_cost_usd": cost_usd, "roi_accepted_per_1k_tokens": run_record["roi_accepted_per_1k_tokens"], "roi_score_per_dollar": run_record["roi_score_per_dollar"]}


def improve_single_ad(ad_id: str, output_dir: str, quality_threshold: float = None):
    """Run one improvement step on a single ad from output/ads_dataset.json. Returns updated ad record or None."""
    out_dir = Path(output_dir)
    path = out_dir / "ads_dataset.json"
    if not path.exists():
        return None
    with open(path) as f:
        ads = json.load(f)
    if not isinstance(ads, list):
        return None
    idx = next((i for i, a in enumerate(ads) if a.get("id") == ad_id), None)
    if idx is None:
        return None
    ad_record = ads[idx]
    brief = ad_record.get("brief") or {}
    ad_copy = ad_record.get("ad_copy") or ad_record.get("ad") or {}
    if not ad_copy:
        return None
    if quality_threshold is None:
        quality_threshold = QUALITY_THRESHOLD
    backend = _infer_backend()
    token_tracker = TokenTracker(backend=backend)
    generator = AdGenerator(seed=42, token_tracker=token_tracker)
    evaluator = Evaluator(seed=42, token_tracker=token_tracker, dimension_weights=DIMENSION_WEIGHTS)
    engine = IterationEngine(generator=generator, evaluator=evaluator, quality_threshold=quality_threshold, max_iterations=2)
    result = engine.run_one_improvement(ad_copy, brief)
    prev_scores = result["history"][0]["evaluation"].get("scores", {})
    weak = min(prev_scores, key=lambda d: prev_scores.get(d, 10)) if prev_scores else None
    existing_history = list(ad_record.get("iteration_history", []))
    # Save previous version's ad copy + scores into the history entry
    new_entry = {
        "iteration": len(existing_history) + 1,
        "overall_score": result["evaluation"].get("overall_score"),
        "scores": result["evaluation"].get("scores", {}),
        "targeted_dimension": weak,
        "previous_ad_copy": dict(ad_copy),  # preserve previous version
        "previous_overall_score": ad_record.get("overall_score"),
    }
    updated_record = {
        "id": ad_id,
        "brief": brief,
        "ad_copy": result["ad"],
        "scores": result["evaluation"]["scores"],
        "overall_score": result["evaluation"]["overall_score"],
        "confidence": result["evaluation"].get("confidence"),
        "dimensions": result["evaluation"].get("dimensions"),
        "iteration_count": len(existing_history) + 1,
        "accepted": result["evaluation"]["overall_score"] >= quality_threshold,
        "iteration_history": existing_history + [new_entry],
    }
    ads[idx] = updated_record
    try:
        export_ads_dataset(ads, path)
        export_evaluation_report(ads, out_dir / "evaluation_report.csv")
        export_evaluation_summary(ads, out_dir / "evaluation_summary.txt", quality_threshold=quality_threshold)
    except Exception as e:
        logger.warning("Could not save improved ad: %s", e)
    return updated_record


