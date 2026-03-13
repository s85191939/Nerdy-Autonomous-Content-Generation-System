"""Web interface for Facebook Ad Engine."""

import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
import csv
import json as _json
from flask import Flask, jsonify, render_template_string, request, send_file, send_from_directory

# Load .env from project root so OPENROUTER_API_KEY etc. are available
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add project root for ad_engine imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ad_engine.cli import run_pipeline, improve_single_ad

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# Shared run state (single run at a time)
_run_state = {
    "status": "idle",  # idle | running | done | error
    "current": 0,
    "total": 0,
    "message": "",
    "result": None,
    "error": None,
    "completed_ads": [],  # list of {id, ad_copy, overall_score, accepted, iteration_count} as each ad finishes
}


def _progress_callback(current, total, message, completed_ad=None):
    _run_state["current"] = current
    _run_state["total"] = total
    _run_state["message"] = message
    if completed_ad is not None:
        _run_state["completed_ads"].append(completed_ad)


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/api/status")
def api_status():
    return jsonify(_run_state)


@app.route("/api/run", methods=["POST"])
def api_run():
    global _run_state
    if _run_state["status"] == "running":
        return jsonify({"ok": False, "error": "A run is already in progress"}), 409
    data = request.get_json(force=True, silent=True) or {}
    num_ads = min(max(1, int(data.get("num_ads", 5))), 100)
    max_iterations = min(max(1, int(data.get("max_iterations", 3))), 10)
    seed = int(data.get("seed", 42))
    enable_image_gen = bool(data.get("enable_image_gen"))
    quality_threshold = data.get("quality_threshold")
    if quality_threshold is not None:
        try:
            quality_threshold = float(quality_threshold)
        except (TypeError, ValueError):
            quality_threshold = None
    dimension_weights = data.get("dimension_weights")
    if dimension_weights is not None and not isinstance(dimension_weights, dict):
        dimension_weights = None
    output_dir = str(ROOT / "output")
    custom_brief = None
    # All brief fields are required (validated client-side)
    audience = (data.get("audience") or "").strip()
    product = (data.get("product") or "").strip()
    goal = (data.get("goal") or "").strip()
    brand_name = (data.get("brand_name") or "").strip()
    tone = (data.get("tone") or "").strip()
    if not all([audience, product, goal, brand_name]):
        return jsonify({"ok": False, "error": "Brand name, audience, product, and goal are required"}), 400
    custom_brief = {
        "audience": audience,
        "product": product,
        "goal": goal,
        "brand_name": brand_name,
    }
    if tone:
        custom_brief["tone"] = tone
    additional_context = (data.get("additional_context") or "").strip()
    if additional_context:
        custom_brief["additional_context"] = additional_context

    # Optional: set API keys from request (not persisted; used only for this process)
    api_key = (data.get("api_key") or "").strip()
    openrouter_key = (data.get("openrouter_api_key") or "").strip()
    openrouter_model = (data.get("openrouter_model") or "").strip() or "google/gemini-2.0-flash-001"
    openai_key = (data.get("openai_api_key") or "").strip()
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    # Only override OpenRouter from form when user actually entered a key (full key in .env used when blank)
    if openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
        os.environ["OPENROUTER_MODEL"] = openrouter_model
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    # Racing: when multiple keys are set, backends race in parallel for speed

    _run_state.update(
        status="running",
        current=0,
        total=num_ads,
        message="Starting...",
        result=None,
        error=None,
        completed_ads=[],
    )

    def run():
        global _run_state
        try:
            result = run_pipeline(
                num_ads=num_ads,
                max_iterations=max_iterations,
                output_dir=output_dir,
                seed=seed,
                progress_callback=_progress_callback,
                custom_brief=custom_brief,
                quality_threshold=quality_threshold,
                dimension_weights=dimension_weights,
                num_variants=1,
                enable_image_gen=enable_image_gen,
                concurrency=4,
            )
            _run_state["status"] = "done"
            _run_state["current"] = num_ads
            _run_state["message"] = "Done."
            _run_state["result"] = result
        except Exception as e:
            _run_state["status"] = "error"
            _run_state["error"] = str(e)
            _run_state["message"] = "Error"

    thread = threading.Thread(target=run)
    thread.start()
    return jsonify({"ok": True, "message": "Run started"})


@app.route("/api/outputs")
def api_outputs():
    out = ROOT / "output"
    if not out.exists():
        return jsonify({"files": [], "run_id": None, "run_timestamp": None})
    files = []
    for name in ["ads_dataset.json", "evaluation_report.csv", "evaluation_summary.txt", "iteration_quality_chart.png"]:
        p = out / name
        if p.exists():
            files.append({
                "name": name,
                "size": p.stat().st_size,
                "description": _OUTPUT_DESCRIPTIONS.get(name, ""),
            })
    run_id = None
    run_timestamp = None
    try:
        hist_path = out / "run_history.json"
        if hist_path.exists():
            with open(hist_path) as f:
                history = _json.load(f)
            if isinstance(history, list) and history:
                last = history[-1]
                run_id = last.get("run_id")
                run_timestamp = last.get("timestamp")
    except Exception:
        pass
    return jsonify({"files": files, "run_id": run_id, "run_timestamp": run_timestamp})


@app.route("/api/output/<path:name>")
def api_output_file(name):
    if name not in ("ads_dataset.json", "evaluation_report.csv", "evaluation_summary.txt", "iteration_quality_chart.png"):
        return "Forbidden", 403
    inline = request.args.get("inline", "").lower() in ("1", "true", "yes")
    path = ROOT / "output" / name
    if not path.exists():
        return "Not found", 404
    if name == "iteration_quality_chart.png" and inline:
        return send_file(path, mimetype="image/png", as_attachment=False)
    return send_from_directory(ROOT / "output", name, as_attachment=True)


@app.route("/api/creatives/<path:filename>")
def api_creative_image(filename):
    """Serve a generated ad image from output/creatives/ or output/runs/*/creatives/ (v2 image gen)."""
    if ".." in filename or filename.startswith("/"):
        return "Forbidden", 403
    # Try flat output/creatives/ first
    path = ROOT / "output" / "creatives" / filename
    if path.exists() and path.is_file():
        return send_file(path, mimetype="image/png", as_attachment=False)
    # Try inside run dirs (search latest first)
    runs_dir = ROOT / "output" / "runs"
    if runs_dir.exists():
        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            cand = run_dir / "creatives" / filename
            if cand.exists() and cand.is_file():
                return send_file(cand, mimetype="image/png", as_attachment=False)
    return "Not found", 404


@app.route("/api/runs/<run_id>/creatives/<path:filename>")
def api_run_creative_image(run_id, filename):
    """Serve a generated ad image from a specific run's creatives directory."""
    if ".." in run_id or "/" in run_id or ".." in filename or filename.startswith("/"):
        return "Forbidden", 403
    path = ROOT / "output" / "runs" / run_id / "creatives" / filename
    if not path.exists() or not path.is_file():
        return "Not found", 404
    download = request.args.get("download", "").lower() in ("1", "true", "yes")
    return send_file(path, mimetype="image/png", as_attachment=download, download_name=filename if download else None)


# --- Result data for in-UI display (so users see what they're downloading) ---

_OUTPUT_DESCRIPTIONS = {
    "ads_dataset.json": "Full ad copy, per-dimension scores, and iteration history for each ad (JSON).",
    "evaluation_report.csv": "Per-ad scores table: ad_id, overall_score, iteration_count, and all 5 dimensions (CSV).",
    "evaluation_summary.txt": "Run summary: total ads, accepted count, average score, quality trend note (text).",
    "iteration_quality_chart.png": "Quality trend chart: average score over run cycles (PNG).",
}
_ALLOWED_RUN_OUTPUT_NAMES = ("ads_dataset.json", "evaluation_report.csv", "evaluation_summary.txt", "iteration_quality_chart.png")


@app.route("/api/result/ads_dataset")
def api_result_ads_dataset():
    """Return current run's ads_dataset.json for in-UI display (full copy, scores, iteration history).

    Uses the root output/ads_dataset.json (always overwritten by the latest run).
    """
    root_path = ROOT / "output" / "ads_dataset.json"
    if root_path.exists():
        try:
            with open(root_path) as f:
                data = _json.load(f)
            return jsonify(data if isinstance(data, list) else [])
        except Exception:
            pass
    return jsonify([])


@app.route("/api/result/summary")
def api_result_summary():
    """Return last run's evaluation_summary.txt for in-UI display."""
    path = ROOT / "output" / "evaluation_summary.txt"
    if not path.exists():
        return "", 404
    try:
        return path.read_text()
    except Exception:
        return "", 404


@app.route("/api/result/chart")
def api_result_chart():
    """Serve quality chart image for inline display (not as download)."""
    path = ROOT / "output" / "iteration_quality_chart.png"
    if not path.exists():
        return "", 404
    return send_file(path, mimetype="image/png", as_attachment=False)


@app.route("/api/result/evaluation_report")
def api_result_evaluation_report():
    """Return last run's evaluation_report.csv as JSON for in-UI table."""
    path = ROOT / "output" / "evaluation_report.csv"
    if not path.exists():
        return jsonify([])
    try:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        return jsonify(rows)
    except Exception:
        return jsonify([])


@app.route("/api/improve_ad", methods=["POST"])
def api_improve_ad():
    """Run one improvement step on a single ad. Body: { ad_id, quality_threshold?, user_context? }."""
    if _run_state["status"] == "running":
        return jsonify({"ok": False, "error": "A run is in progress"}), 409
    data = request.get_json(force=True, silent=True) or {}
    ad_id = (data.get("ad_id") or "").strip()
    if not ad_id or ".." in ad_id or "/" in ad_id:
        return jsonify({"ok": False, "error": "Invalid ad_id"}), 400
    qt = data.get("quality_threshold")
    try:
        qt = float(qt) if qt is not None else None
    except (TypeError, ValueError):
        qt = None
    user_context = (data.get("user_context") or "").strip() or None
    updated = improve_single_ad(ad_id, str(ROOT / "output"), quality_threshold=qt, user_context=user_context)
    if updated is None:
        return jsonify({"ok": False, "error": "Ad not found or no run output"}), 404
    return jsonify({"ok": True, "ad": updated})


@app.route("/api/extract_pdf", methods=["POST"])
def api_extract_pdf():
    """Extract text from an uploaded PDF file. Returns { ok, text }."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "Only PDF files are supported"}), 400
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(f.stream)
        text_parts = []
        for page in reader.pages[:50]:  # cap at 50 pages
            t = page.extract_text()
            if t:
                text_parts.append(t.strip())
        text = "\n\n".join(text_parts)
        if len(text) > 20000:
            text = text[:20000] + "\n\n[...truncated at 20,000 characters]"
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"PDF extraction failed: {e}"}), 500


@app.route("/api/fetch_pdf_url", methods=["POST"])
def api_fetch_pdf_url():
    """Fetch a PDF from a URL and extract text. Body: { url }."""
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "URL is required"}), 400
    try:
        import PyPDF2
        import io
        r = __import__("requests").get(url, timeout=15, headers={"User-Agent": "FacebookAdEngine/1.0"})
        r.raise_for_status()
        reader = PyPDF2.PdfReader(io.BytesIO(r.content))
        text_parts = []
        for page in reader.pages[:50]:
            t = page.extract_text()
            if t:
                text_parts.append(t.strip())
        text = "\n\n".join(text_parts)
        if len(text) > 20000:
            text = text[:20000] + "\n\n[...truncated at 20,000 characters]"
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to fetch/extract PDF: {e}"}), 500


@app.route("/api/run_history")
def api_run_history():
    """Return run history for dashboard. Ensures each run has run_id; merges campaign names."""
    import json
    path = ROOT / "output" / "run_history.json"
    if not path.exists():
        return jsonify([])
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return jsonify([])
        names_path = ROOT / "output" / "campaign_names.json"
        names = {}
        if names_path.exists():
            try:
                with open(names_path) as nf:
                    names = json.load(nf)
            except Exception:
                pass
        for r in data:
            if not r.get("run_id") and r.get("timestamp"):
                ts = r["timestamp"].replace("-", "").replace(":", "").replace("Z", "").replace(".", "")[:15]
                r["run_id"] = ts
            r["name"] = names.get(r.get("run_id") or "", "").strip() or None
            run_id = r.get("run_id")
            r["outputs"] = []
            if run_id and ".." not in run_id and "/" not in run_id:
                run_dir = ROOT / "output" / "runs" / run_id
                if run_dir.exists() and run_dir.is_dir():
                    for name in _ALLOWED_RUN_OUTPUT_NAMES:
                        p = run_dir / name
                        if p.exists():
                            r["outputs"].append({"name": name, "size": p.stat().st_size})
        return jsonify(data)
    except Exception:
        return jsonify([])


@app.route("/api/runs/<run_id>/ads")
def api_run_ads(run_id):
    """Return ads for a specific run (drill-down)."""
    import json
    if ".." in run_id or "/" in run_id:
        return jsonify({"error": "Invalid run_id"}), 400
    path = ROOT / "output" / "runs" / run_id / "ads_dataset.json"
    if not path.exists():
        return jsonify([])
    try:
        with open(path) as f:
            data = json.load(f)
        return jsonify(data if isinstance(data, list) else [])
    except Exception:
        return jsonify([])


@app.route("/api/runs/<run_id>/outputs")
def api_run_outputs(run_id):
    """List output files for a specific run (for dashboard per-run downloads)."""
    if ".." in run_id or "/" in run_id:
        return jsonify({"files": []}), 400
    run_dir = ROOT / "output" / "runs" / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        return jsonify({"files": []})
    files = []
    for name in _ALLOWED_RUN_OUTPUT_NAMES:
        p = run_dir / name
        if p.exists():
            files.append({"name": name, "size": p.stat().st_size, "description": _OUTPUT_DESCRIPTIONS.get(name, "")})
    return jsonify({"files": files, "run_id": run_id})


@app.route("/api/runs/<run_id>/output/<path:name>")
def api_run_output_file(run_id, name):
    """Download an output file from a specific run."""
    if ".." in run_id or "/" in run_id or name not in _ALLOWED_RUN_OUTPUT_NAMES:
        return "Forbidden", 403
    path = ROOT / "output" / "runs" / run_id / name
    if not path.exists():
        return "Not found", 404
    if name == "iteration_quality_chart.png" and request.args.get("inline", "").lower() in ("1", "true", "yes"):
        return send_file(path, mimetype="image/png", as_attachment=False)
    return send_file(path, as_attachment=True, download_name=name)


@app.route("/api/campaign_name", methods=["POST"])
def api_campaign_name():
    """Set display name for a run. Body: { run_id, name }."""
    import json
    data = request.get_json(force=True, silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    name = (data.get("name") or "").strip()
    if not run_id or ".." in run_id or "/" in run_id:
        return jsonify({"ok": False, "error": "Invalid run_id"}), 400
    path = ROOT / "output" / "campaign_names.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    names = {}
    if path.exists():
        try:
            with open(path) as f:
                names = json.load(f)
        except Exception:
            pass
    names[run_id] = name
    try:
        with open(path, "w") as f:
            json.dump(names, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/iterate_campaign", methods=["POST"])
def api_iterate_campaign():
    global _run_state
    if _run_state["status"] == "running":
        return jsonify({"ok": False, "error": "A run is already in progress"}), 409
    data = request.get_json(force=True, silent=True) or {}
    run_id = (data.get("run_id") or "").strip()
    max_extra = min(max(1, int(data.get("max_extra_iterations", 3))), 10)
    if not run_id or ".." in run_id or "/" in run_id:
        return jsonify({"ok": False, "error": "Invalid run_id"}), 400
    from ad_engine.cli import iterate_campaign
    _run_state.update(status="running", current=0, total=1, message="Re-iterating...", result=None, error=None, completed_ads=[])
    def run():
        global _run_state
        try:
            result = iterate_campaign(str(ROOT / "output"), run_id=run_id, max_extra_iterations=max_extra, progress_callback=_progress_callback)
            _run_state["status"] = "done"
            _run_state["result"] = result
            _run_state["current"] = result.get("num_ads", 0)
            _run_state["total"] = result.get("num_ads", 1)
        except Exception as e:
            _run_state["status"] = "error"
            _run_state["error"] = str(e)
    threading.Thread(target=run).start()
    return jsonify({"ok": True})


@app.route("/api/competitor/insights")
def api_competitor_insights():
    from ad_engine.competitor.insights import load_insights
    return jsonify(load_insights(ROOT / "output" / "competitor_insights.json"))


@app.route("/api/competitor/extract", methods=["POST"])
def api_competitor_extract():
    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data.get("ads"), list):
        return jsonify({"ok": False, "error": "Send { ads: [...] }"}), 400
    from ad_engine.competitor.insights import extract_patterns, save_insights
    insights = extract_patterns(data["ads"])
    save_insights(insights, ROOT / "output" / "competitor_insights.json")
    return jsonify({"ok": True, "insights": insights})


@app.route("/api/competitor/rewrite", methods=["POST"])
def api_competitor_rewrite():
    data = request.get_json(force=True, silent=True) or {}
    ad = data.get("ad")
    if not ad or not isinstance(ad, dict):
        return jsonify({"ok": False, "error": "Send { ad: {...} }"}), 400
    from ad_engine.competitor.insights import rewrite_as_brand
    out = rewrite_as_brand(ad)
    return jsonify({"ok": out is not None, "ad": out} if out else {"ok": False, "error": "Rewrite failed"})


@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Facebook Ad Engine — AI Ad Copy for Facebook & Instagram</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com?plugins=forms"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { sans: ['DM Sans', 'system-ui', 'sans-serif'] },
          colors: {
            primary: { 50: '#ecfdf5', 100: '#d1fae5', 200: '#a7f3d0', 300: '#6ee7b7', 400: '#34d399', 500: '#10b981', 600: '#059669', 700: '#047857', 800: '#065f46', 900: '#064e3b' },
            surface: { 50: '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 800: '#1e293b', 900: '#0f172a' }
          }
        }
      }
    }
  </script>
  <style type="text/tailwindcss">
    @layer utilities {
      .progress-fill { transition: width 0.3s ease-out; }
    }
  </style>
  <style>
    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }
    .progress-indeterminate {
      background: linear-gradient(90deg, #10b981 25%, #34d399 50%, #10b981 75%);
      background-size: 200% 100%;
      animation: shimmer 1.5s ease-in-out infinite;
    }
    @keyframes pulse-dot {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }
    .pulse-dot { animation: pulse-dot 1s ease-in-out infinite; }
    @keyframes spin-slow {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    .spin-slow { animation: spin-slow 1.5s linear infinite; }
  </style>
</head>
<body class="min-h-screen bg-surface-50 text-slate-800 font-sans antialiased">
  <!-- Header -->
  <header class="border-b border-slate-200/80 bg-white/90 backdrop-blur-sm sticky top-0 z-10">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-xl font-bold tracking-tight text-slate-900">Facebook</span>
        <span class="text-xl font-semibold text-primary-600">Ad Engine</span>
        <span class="hidden sm:inline-flex items-center rounded-full bg-primary-50 text-primary-700 text-xs font-medium px-2 py-0.5 ml-1">AI-Powered</span>
      </div>
      <nav class="flex items-center gap-1">
        <a href="/" class="px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-50 text-primary-700">Generator</a>
        <a href="/dashboard" class="px-3 py-1.5 text-sm font-medium rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-800 transition-colors">Campaigns</a>
        <span class="px-3 py-1.5 text-sm font-medium rounded-lg text-slate-400 cursor-not-allowed select-none" title="Coming soon">Studio <span class="text-[10px] bg-slate-100 text-slate-400 px-1.5 py-0.5 rounded-md ml-0.5 uppercase tracking-wider">TBA</span></span>
      </nav>
    </div>
  </header>

  <main class="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
    <!-- Hero -->
    <section class="text-center mb-8 sm:mb-10">
      <h1 class="text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight mb-3">Generate ad copy that performs</h1>
      <p class="text-base text-slate-500 max-w-lg mx-auto mb-4">AI-powered Facebook &amp; Instagram ad generation with LLM-as-judge evaluation. We generate, score, and iterate until every ad hits your quality bar.</p>
      <div class="flex flex-wrap items-center justify-center gap-2 text-xs">
        <span class="inline-flex items-center rounded-full bg-primary-50 text-primary-700 px-2.5 py-1 font-medium">LLM-as-Judge Eval</span>
        <span class="inline-flex items-center rounded-full bg-blue-50 text-blue-700 px-2.5 py-1 font-medium">Auto-Iteration</span>
        <span class="inline-flex items-center rounded-full bg-purple-50 text-purple-700 px-2.5 py-1 font-medium">Multi-Model</span>
        <span class="inline-flex items-center rounded-full bg-amber-50 text-amber-700 px-2.5 py-1 font-medium">Quality Ratchet</span>
        <span class="inline-flex items-center rounded-full bg-rose-50 text-rose-700 px-2.5 py-1 font-medium">Competitive Intel</span>
      </div>
    </section>

    <!-- Generator card -->
    <section class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden mb-6">
      <div class="px-6 py-5 border-b border-slate-100">
        <h2 class="text-lg font-semibold text-slate-900">Generate from a brief</h2>
        <p class="text-sm text-slate-500 mt-0.5">Enter your brand, audience, product, and goal to generate ads. All brief fields are required.</p>
      </div>
      <form id="form" class="p-6 space-y-5">
        <div class="bg-slate-50 rounded-lg p-4 border border-slate-200">
          <p class="text-sm font-semibold text-slate-800 mb-3">Brief (audience + product + goal)</p>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label for="brand_name" class="block text-sm font-medium text-slate-700 mb-1">Brand name <span class="text-red-500">*</span></label>
              <input type="text" id="brand_name" name="brand_name" placeholder="e.g. MovieMagic, Nike, Acme Corp" required
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
            <div>
              <label for="audience" class="block text-sm font-medium text-slate-700 mb-1">Audience <span class="text-red-500">*</span></label>
              <input type="text" id="audience" name="audience" placeholder="e.g. Parents of high school juniors" required
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
            <div>
              <label for="product" class="block text-sm font-medium text-slate-700 mb-1">Product / offer <span class="text-red-500">*</span></label>
              <input type="text" id="product" name="product" placeholder="e.g. SAT tutoring program" required
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
            <div>
              <label for="goal" class="block text-sm font-medium text-slate-700 mb-1">Goal <span class="text-red-500">*</span></label>
              <input type="text" id="goal" name="goal" placeholder="e.g. conversion or awareness" required
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
            <div>
              <label for="tone" class="block text-sm font-medium text-slate-700 mb-1">Tone (optional)</label>
              <input type="text" id="tone" name="tone" placeholder="e.g. reassuring, results-focused"
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
          </div>
          <!-- Additional context textarea -->
          <div class="mt-4">
            <label for="additional_context" class="block text-sm font-medium text-slate-700 mb-1">Dream panel (optional)</label>
            <textarea id="additional_context" name="additional_context" rows="3"
              placeholder="Paste any extra info here — brand guidelines, reference copy, competitor ads, landing page text, key selling points, or anything else the AI should know..."
              class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm resize-y"></textarea>
            <p class="text-xs text-slate-400 mt-1">The more context you provide, the better the ads. Paste URLs, brand docs, or reference copy.</p>
          </div>
        </div>
        <!-- v2: Image generation toggle (hidden — v1 focus) -->
        <div class="hidden">
          <input type="checkbox" id="enable_image_gen" name="enable_image_gen" value="1"
            class="rounded border-slate-300 text-primary-600 focus:ring-primary-500 w-4 h-4">
        </div>
        <!-- Quick settings + Generate button -->
        <div class="flex flex-col sm:flex-row gap-4 items-end">
          <div class="flex-1 grid grid-cols-2 gap-4">
            <div>
              <label for="num_ads" class="block text-sm font-medium text-slate-700 mb-1.5">Number of ads</label>
              <input type="number" id="num_ads" name="num_ads" value="5" min="1" max="100"
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
            <div>
              <label for="quality_threshold" class="block text-sm font-medium text-slate-700 mb-1.5">Quality target</label>
              <input type="number" id="quality_threshold" name="quality_threshold" step="0.1" min="1" max="10" value="7.0"
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
          </div>
          <div class="shrink-0 pb-px">
            <button type="submit" id="runBtn"
              class="inline-flex items-center justify-center gap-2 px-8 py-2.5 bg-primary-600 text-white font-semibold rounded-lg shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed transition-colors">
              <svg id="runIcon" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <span id="runLabel">Generate ads</span>
            </button>
          </div>
        </div>
        <!-- Advanced settings (collapsed by default) -->
        <details class="border-t border-slate-100 pt-3">
          <summary class="text-sm font-medium text-slate-500 cursor-pointer hover:text-slate-700 select-none flex items-center gap-1.5 py-1">
            <svg class="w-4 h-4 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            Advanced settings
          </summary>
          <div class="mt-4 space-y-5">
            <!-- max_iterations hidden: use "Make it better" to iterate manually -->
            <input type="hidden" id="max_iterations" name="max_iterations" value="3">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label for="seed" class="block text-sm font-medium text-slate-700 mb-1.5">Random seed</label>
                <input type="number" id="seed" name="seed" value="42"
                  class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
              </div>
            </div>
            <div class="border-t border-slate-100 pt-4">
              <p class="text-sm font-medium text-slate-700 mb-3">API configuration</p>
              <p class="text-xs text-slate-500 mb-3">Keys from <code class="bg-slate-100 px-1 rounded">.env</code> are used when fields are left blank.</p>
              <div class="space-y-3">
                <div>
                  <label for="api_key" class="block text-sm font-medium text-slate-600 mb-1">Gemini API key</label>
                  <input type="password" id="api_key" name="api_key" placeholder="Optional — uses .env" autocomplete="off"
                    class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
                </div>
                <div>
                  <label for="openai_api_key" class="block text-sm font-medium text-slate-600 mb-1">OpenAI API key <span class="text-slate-400 font-normal">(adds speed — races Gemini + OpenAI in parallel)</span></label>
                  <input type="password" id="openai_api_key" name="openai_api_key" placeholder="Optional — uses .env" autocomplete="off"
                    class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label for="openrouter_api_key" class="block text-sm font-medium text-slate-600 mb-1">OpenRouter key</label>
                    <input type="text" id="openrouter_api_key" name="openrouter_api_key" placeholder="Leave blank to use .env" autocomplete="off"
                      class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm font-mono">
                  </div>
                  <div>
                    <label for="openrouter_model" class="block text-sm font-medium text-slate-600 mb-1">Model</label>
                    <input type="text" id="openrouter_model" name="openrouter_model" value="google/gemini-2.0-flash-001" placeholder="google/gemini-2.0-flash-001"
                      class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
                  </div>
                </div>
              </div>
            </div>
          </div>
        </details>
      </form>
    </section>

    <!-- Related Ads from Facebook Ad Library -->
    <section id="adLibraryCard" class="hidden bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden mb-6">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">Related ads on Facebook</h3>
          <p class="text-sm text-slate-500 mt-0.5">See what competitors are running right now in the Facebook Ad Library.</p>
        </div>
        <svg class="w-6 h-6 text-blue-500 shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
      </div>
      <div class="p-6">
        <div id="adLibraryLinks" class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4"></div>
        <div id="adLibraryIframe" class="mt-4 hidden">
          <div class="border border-slate-200 rounded-xl overflow-hidden bg-slate-50">
            <div class="flex items-center justify-between px-4 py-2 bg-slate-100 border-b border-slate-200">
              <span class="text-xs font-medium text-slate-600" id="adLibraryIframeLabel">Facebook Ad Library</span>
              <a id="adLibraryExternalLink" href="#" target="_blank" rel="noopener" class="text-xs text-primary-600 hover:underline font-medium">Open in new tab</a>
            </div>
            <iframe id="adLibraryFrame" class="w-full border-0" style="height:600px" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-3">Powered by <a href="https://www.facebook.com/ads/library/" target="_blank" rel="noopener" class="text-blue-500 hover:underline">Meta Ad Library</a>. Results open in a new tab for full browsing.</p>
      </div>
    </section>

    <!-- Progress (hidden by default) -->
    <section id="progressCard" class="hidden bg-white rounded-2xl shadow-sm border border-slate-200/80 p-6 mb-6">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <svg id="progressSpinner" class="w-5 h-5 text-primary-500 spin-slow" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <h3 id="progressTitle" class="text-sm font-semibold text-slate-700">Generating ads</h3>
        </div>
        <span id="progressPct" class="text-sm font-medium text-primary-600">0%</span>
      </div>
      <div class="h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div id="progressFill" class="progress-fill h-full bg-primary-500 rounded-full" style="width:0%"></div>
      </div>
      <div class="flex items-center justify-between mt-2">
        <p id="progressText" class="text-sm text-slate-500">—</p>
        <p id="progressElapsed" class="text-xs text-slate-400 tabular-nums"></p>
      </div>
      <!-- Stage indicators -->
      <div id="progressStages" class="mt-4 flex items-center gap-1 text-xs flex-wrap">
        <span id="stage-generate" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">
          <span class="w-1.5 h-1.5 rounded-full bg-current"></span> Generate
        </span>
        <svg class="w-3 h-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        <span id="stage-evaluate" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">
          <span class="w-1.5 h-1.5 rounded-full bg-current"></span> Score
        </span>
        <svg class="w-3 h-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        <span id="stage-improve" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">
          <span class="w-1.5 h-1.5 rounded-full bg-current"></span> Improve
        </span>
        <svg class="w-3 h-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        <span id="stage-done" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">
          <span class="w-1.5 h-1.5 rounded-full bg-current"></span> Done
        </span>
      </div>
      <div id="liveAdsWrap" class="mt-6 pt-4 border-t border-slate-100">
        <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Ads created so far</h4>
        <div id="liveAdsList" class="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-96 overflow-y-auto"></div>
      </div>
    </section>

    <!-- Result (hidden by default) -->
    <section id="resultCard" class="hidden mb-6">
      <h3 class="text-lg font-semibold text-slate-900 mb-4">Run result</h3>
      <div id="resultBody" class="grid grid-cols-2 sm:grid-cols-4 gap-3"></div>
      <p id="resultError" class="hidden mt-4 p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm"></p>
    </section>

    <!-- Generated ads: full copy visible as each ad completes (paginated) -->
    <section id="generatedAdsCard" class="hidden mb-6">
      <h3 class="text-lg font-semibold text-slate-900 mb-1">Your generated ads</h3>
      <p class="text-sm text-slate-500 mb-4">Ads appear below as each one finishes. Expand an ad for scores and iteration history. Paginate through results as they come in.</p>
      <div id="paginationBar" class="hidden flex items-center justify-between gap-4 mb-4 flex-wrap">
        <p id="paginationText" class="text-sm text-slate-600">Showing 0–0 of 0</p>
        <div class="flex items-center gap-2">
          <button type="button" id="paginationPrev" class="px-3 py-1.5 rounded-lg border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed">Prev</button>
          <button type="button" id="paginationNext" class="px-3 py-1.5 rounded-lg border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed">Next</button>
        </div>
      </div>
      <div id="generatedAdsList" class="space-y-4"></div>
    </section>

    <!-- Evaluation summary (visible after run) -->
    <section id="summaryCard" class="hidden mb-6 bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100">
        <h3 class="text-lg font-semibold text-slate-900">Evaluation summary</h3>
        <p class="text-sm text-slate-500 mt-0.5">Same content as evaluation_summary.txt — what you see is what you download.</p>
      </div>
      <pre id="summaryText" class="p-6 text-sm text-slate-700 whitespace-pre-wrap font-sans overflow-x-auto"></pre>
    </section>

    <!-- Quality trend chart (visible after run) — dynamic, updates after each improvement -->
    <section id="chartCard" class="hidden mb-6 bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100">
        <h3 class="text-lg font-semibold text-slate-900">Quality trend</h3>
        <p class="text-sm text-slate-500 mt-0.5">Average score across all ads — updates live after each improvement.</p>
      </div>
      <div class="p-6">
        <canvas id="qualityChart" width="700" height="280" style="max-width:100%;"></canvas>
      </div>
    </section>

    <!-- Scores table (visible after run) -->
    <section id="scoresTableCard" class="hidden mb-6 bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100">
        <h3 class="text-lg font-semibold text-slate-900">Scores table</h3>
        <p class="text-sm text-slate-500 mt-0.5">Per-ad scores — same columns as evaluation_report.csv.</p>
      </div>
      <div class="overflow-x-auto"><table id="scoresTable" class="w-full text-sm text-left border-collapse"></table></div>
    </section>

    <!-- Output files (hidden by default) — click to expand preview -->
    <section id="outputsCard" class="hidden bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100">
        <h3 class="text-lg font-semibold text-slate-900">Campaign outputs</h3>
        <p id="outputsRunInfo" class="text-sm text-slate-600 mt-0.5">Current run — click any file to preview, or download directly.</p>
        <p class="text-xs text-slate-500 mt-0.5">All runs and their downloads are also on the <a href="/dashboard" class="text-primary-600 hover:underline">Dashboard</a>.</p>
      </div>
      <div id="outputList" class="divide-y divide-slate-100"></div>
    </section>
  </main>


  <footer class="border-t border-slate-200 mt-12 py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 text-center text-sm text-slate-500">
      Facebook Ad Engine for copy that actually works.
    </div>
  </footer>

  <script>
    const form = document.getElementById('form');
    const runBtn = document.getElementById('runBtn');
    const runLabel = document.getElementById('runLabel');
    const runIcon = document.getElementById('runIcon');
    const progressCard = document.getElementById('progressCard');
    const progressFill = document.getElementById('progressFill');
    const progressPct = document.getElementById('progressPct');
    const progressText = document.getElementById('progressText');
    const progressElapsed = document.getElementById('progressElapsed');
    const progressTitle = document.getElementById('progressTitle');
    const stageGenerate = document.getElementById('stage-generate');
    const stageEvaluate = document.getElementById('stage-evaluate');
    const stageDone = document.getElementById('stage-done');
    const resultCard = document.getElementById('resultCard');
    const resultBody = document.getElementById('resultBody');
    const resultError = document.getElementById('resultError');
    const outputsCard = document.getElementById('outputsCard');
    const outputList = document.getElementById('outputList');
    const liveAdsList = document.getElementById('liveAdsList');
    const generatedAdsCard = document.getElementById('generatedAdsCard');
    const generatedAdsList = document.getElementById('generatedAdsList');
    const paginationBar = document.getElementById('paginationBar');
    const paginationText = document.getElementById('paginationText');
    const paginationPrev = document.getElementById('paginationPrev');
    const paginationNext = document.getElementById('paginationNext');

    let pollTimer = null;
    let allCompletedAds = [];
    let currentPage = 1;
    let runStartTime = null;
    const PAGE_SIZE = 5;

    const stageImprove = document.getElementById('stage-improve');
    function setStage(stage) {
      // stage: 'generate', 'evaluate', 'improve', 'done'
      const stages = { generate: stageGenerate, evaluate: stageEvaluate, improve: stageImprove, done: stageDone };
      const order = Object.keys(stages);
      order.forEach(function(k) {
        const el = stages[k];
        if (!el) return;
        if (k === stage) {
          el.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 font-medium pulse-dot';
        } else if (order.indexOf(k) < order.indexOf(stage)) {
          el.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-50 text-primary-600';
        } else {
          el.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-400';
        }
      });
    }

    function updateElapsed() {
      if (!runStartTime || !progressElapsed) return;
      const secs = Math.round((Date.now() - runStartTime) / 1000);
      if (secs < 60) progressElapsed.textContent = secs + 's';
      else progressElapsed.textContent = Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
    }

    function esc(s) {
      if (s == null || s === undefined) return '';
      const d = document.createElement('div');
      d.textContent = String(s);
      return d.innerHTML;
    }

    function renderLiveAds(completedAds) {
      if (!liveAdsList) return;
      if (!completedAds || completedAds.length === 0) {
        liveAdsList.innerHTML = '<p class="text-sm text-slate-400 col-span-full">No ads yet…</p>';
        return;
      }
      liveAdsList.innerHTML = completedAds.map(function(ad) {
        const copy = ad.ad_copy || {};
        const headline = esc(copy.headline || '—');
        const primary = esc(copy.primary_text || '');
        const score = ad.overall_score != null ? Number(ad.overall_score) : '—';
        const accepted = ad.accepted ? '<span class="inline-flex items-center rounded-full bg-emerald-100 text-emerald-800 text-xs font-medium px-2 py-0.5">Accepted</span>' : '<span class="inline-flex items-center rounded-full bg-slate-100 text-slate-600 text-xs font-medium px-2 py-0.5">Below threshold</span>';
        return '<div class="rounded-xl border border-slate-200 bg-slate-50/50 p-3 text-left shadow-sm">' +
          '<div class="flex items-start justify-between gap-2">' +
            '<span class="font-semibold text-slate-800 text-sm">' + headline + '</span>' +
            '<span class="text-sm font-bold ' + scoreColor(score) + ' shrink-0">' + score + '</span>' +
          '</div>' +
          '<p class="text-xs text-slate-600 mt-1">' + primary + '</p>' +
          '<div class="mt-2">' + accepted + '</div>' +
          '</div>';
      }).join('');
    }

    function scoreColor(s) {
      if (s == null || s === '—') return 'text-slate-600';
      if (s >= 8) return 'text-emerald-600';
      if (s >= 7) return 'text-primary-600';
      if (s >= 5) return 'text-amber-600';
      return 'text-red-600';
    }
    function scoreBg(s) {
      if (s == null || s === '—') return 'bg-slate-100';
      if (s >= 8) return 'bg-emerald-50 border-emerald-200';
      if (s >= 7) return 'bg-primary-50 border-primary-200';
      if (s >= 5) return 'bg-amber-50 border-amber-200';
      return 'bg-red-50 border-red-200';
    }

    function renderOneAd(ad, idx) {
      const copy = ad.ad_copy || {};
      const headline = esc(copy.headline || '—');
      const primary = esc(copy.primary_text || '');
      const description = esc(copy.description || '');
      const cta = esc(copy.cta || '');
      const score = ad.overall_score != null ? Number(ad.overall_score) : '—';
      const accepted = ad.accepted;
      const iterCount = ad.iteration_count || 1;
      const badge = accepted ? '<span class="inline-flex items-center rounded-full bg-emerald-100 text-emerald-800 text-xs font-medium px-2 py-0.5">Accepted</span>' : '<span class="inline-flex items-center rounded-full bg-red-100 text-red-700 text-xs font-medium px-2 py-0.5">Below threshold</span>';
      const cycleBadge = iterCount > 1 ? '<span class="inline-flex items-center rounded-full bg-blue-100 text-blue-700 text-xs font-medium px-2 py-0.5">v' + iterCount + '</span>' : '';
      const dims = ad.dimensions || {};
      const dimRows = Object.keys(dims).map(function(d) {
        const o = dims[d];
        const s = o && (o.score != null) ? o.score : (ad.scores && ad.scores[d]);
        const r = o && o.rationale ? esc(o.rationale) : '';
        return '<tr><td class="font-medium text-slate-600 pr-2">' + esc(d) + '</td><td class="pr-2 font-semibold ' + scoreColor(s) + '">' + s + '</td><td class="text-slate-500 text-xs">' + r + '</td></tr>';
      }).join('');
      const hist = ad.iteration_history || [];
      const histRows = hist.map(function(h, i) {
        const t = h.targeted_dimension ? esc(h.targeted_dimension) : '';
        return '<tr><td class="pr-2">' + (h.iteration || i + 1) + '</td><td class="pr-2 font-semibold ' + scoreColor(h.overall_score) + '">' + (h.overall_score != null ? h.overall_score : '—') + '</td><td class="text-slate-500 text-xs">' + t + '</td></tr>';
      }).join('');
      const adId = esc(ad.id || ('ad_' + idx));
      return '<div id="ad-card-' + adId + '" class="ad-card-wrapper">' +
        '<div class="rounded-xl border border-slate-200 bg-white shadow-sm text-left">' +
          '<div class="p-4 flex items-center justify-between gap-2 flex-wrap">' +
            '<span class="text-xs font-medium text-slate-400">' + (ad.id || ('Ad ' + (idx + 1))) + '</span>' +
            '<span class="text-sm font-bold ' + scoreColor(score) + '">Score: ' + score + '</span>' +
            badge + cycleBadge +
            '<span class="text-slate-400 text-xs truncate max-w-[200px]">' + headline + '</span>' +
            '<button type="button" class="improve-ad-btn px-3 py-1.5 rounded-lg bg-primary-600 text-white text-xs font-semibold hover:bg-primary-700 shadow-sm shrink-0 transition-colors" data-ad-id="' + adId + '">Make it better</button>' +
          '</div>' +
          '<div class="px-4 pb-4 border-t border-slate-100">' +
            (copy.image_path ? '<div class="mt-3 bg-slate-50 rounded-lg p-3 border border-slate-200"><img src="/api/creatives/' + esc(copy.image_path.replace('creatives/','')) + '" alt="Generated ad creative" class="rounded-lg border border-slate-200 max-h-96 w-full object-contain"><div class="mt-2 flex items-center gap-2"><a href="/api/creatives/' + esc(copy.image_path.replace('creatives/','')) + '?download=1" download class="inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 border border-primary-200 rounded-lg px-2.5 py-1.5 hover:bg-primary-50">Download image</a><span class="text-xs text-slate-400">1080x1080 PNG</span></div></div>' : '') +
            '<h4 class="font-semibold text-slate-900 mt-3 text-base">' + headline + '</h4>' +
            (primary ? '<p class="text-sm text-slate-700 mt-2 whitespace-pre-wrap">' + primary + '</p>' : '') +
            (description ? '<p class="text-sm text-slate-600 mt-1">' + description + '</p>' : '') +
            (cta ? '<p class="text-sm font-medium text-primary-600 mt-2">CTA: ' + cta + '</p>' : '') +
            (dimRows ? '<div class="mt-4"><p class="text-xs font-semibold text-slate-500 uppercase mb-1">Dimensions</p><table class="w-full text-sm"><tbody>' + dimRows + '</tbody></table></div>' : '') +
            (histRows ? '<div class="mt-3"><p class="text-xs font-semibold text-slate-500 uppercase mb-1">Iteration history</p><table class="w-full text-sm"><thead><tr><th class="text-left pr-2">Cycle</th><th class="text-left pr-2">Score</th><th class="text-left">Targeted</th></tr></thead><tbody>' + histRows + '</tbody></table></div>' : '') +
          '</div>' +
        '</div>' +
        '</div>';
    }

    function renderGeneratedAdsPage(ads, page, pageSize) {
      if (!generatedAdsList) return;
      const total = (ads && ads.length) || 0;
      if (total === 0) {
        generatedAdsList.innerHTML = '<p class="text-sm text-slate-400">No ads yet. Ads will appear here as each one completes.</p>';
        if (paginationBar) paginationBar.classList.add('hidden');
        return;
      }
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      const safePage = Math.max(1, Math.min(page, totalPages));
      const start = (safePage - 1) * pageSize;
      const end = Math.min(start + pageSize, total);
      const slice = ads.slice(start, end);
      generatedAdsList.innerHTML = slice.map(function(ad, i) { return renderOneAd(ad, start + i); }).join('');
      if (paginationBar) {
        paginationBar.classList.remove('hidden');
        paginationText.textContent = 'Showing ' + (start + 1) + '–' + end + ' of ' + total;
        paginationPrev.disabled = safePage <= 1;
        paginationNext.disabled = safePage >= totalPages;
      }
      currentPage = safePage;
    }

    function renderGeneratedAds(completedAds) {
      if (!completedAds || completedAds.length === 0) {
        allCompletedAds = [];
        renderGeneratedAdsPage([], 1, PAGE_SIZE);
        return;
      }
      allCompletedAds = completedAds;
      renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
    }

    function showProgress(show) {
      progressCard.classList.toggle('hidden', !show);
      if (show) {
        runStartTime = Date.now();
        setStage('generate');
        progressFill.classList.add('progress-indeterminate');
        progressFill.style.width = '100%';
        progressPct.textContent = '';
        progressTitle.textContent = 'Generating ads...';
        progressText.textContent = 'Sending to AI model...';
      } else {
        runStartTime = null;
        progressFill.classList.remove('progress-indeterminate');
      }
    }
    function showResult(show) {
      resultCard.classList.toggle('hidden', !show);
    }
    function showOutputs(show) {
      outputsCard.classList.toggle('hidden', !show);
    }
    function showGeneratedAds(show) {
      if (generatedAdsCard) generatedAdsCard.classList.toggle('hidden', !show);
    }

    function statCard(label, value) {
      return '<div class="bg-white rounded-xl border border-slate-200/80 p-4 shadow-sm"><p class="text-xs font-medium text-slate-500 uppercase tracking-wide">' + label + '</p><p class="text-2xl font-bold text-slate-900 mt-1">' + value + '</p></div>';
    }

    function poll() {
      updateElapsed();
      fetch('/api/status').then(r => r.json()).then(data => {
        const total = data.total || 1;
        const msg = data.message || '';

        // Detect stage from message and update UI
        if (msg.indexOf('Generating') >= 0 || msg.indexOf('Starting') >= 0 || msg.indexOf('Sending') >= 0) {
          setStage('generate');
          progressTitle.textContent = 'Generating ads...';
          progressFill.classList.add('progress-indeterminate');
          progressFill.style.width = '100%';
          progressPct.textContent = '';
        } else if (msg.indexOf('Improving') >= 0 || msg.indexOf('improved') >= 0) {
          setStage('improve');
          progressTitle.textContent = 'Iterating below-threshold ads...';
          var pct = Math.round((data.current / total) * 100);
          progressFill.classList.remove('progress-indeterminate');
          progressFill.style.width = pct + '%';
          progressPct.textContent = pct + '% at threshold';
        } else if (msg.indexOf('Evaluat') >= 0 || msg.indexOf('Scor') >= 0) {
          setStage('evaluate');
          progressTitle.textContent = 'Scoring ads...';
          progressFill.classList.add('progress-indeterminate');
          progressFill.style.width = '100%';
          progressPct.textContent = '';
        } else if (data.current > 0) {
          // Per-ad progress (non-batch mode or ads landing)
          const pct = Math.round((data.current / total) * 100);
          progressFill.classList.remove('progress-indeterminate');
          progressFill.style.width = pct + '%';
          progressPct.textContent = pct + '%';
          if (data.current >= total) setStage('done');
          else setStage('evaluate');
          progressTitle.textContent = 'Processing ads...';
        }
        progressText.textContent = msg || data.current + ' / ' + data.total;

        if (data.status === 'running' && data.completed_ads) {
          renderLiveAds(data.completed_ads);
          if (data.completed_ads.length > 0) {
            const prevTotal = allCompletedAds.length;
            allCompletedAds = data.completed_ads;
            if (prevTotal > 0 && allCompletedAds.length > prevTotal) {
              const totalPages = Math.ceil(prevTotal / PAGE_SIZE);
              if (currentPage >= totalPages) currentPage = Math.ceil(allCompletedAds.length / PAGE_SIZE);
            }
            renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
            showGeneratedAds(true);
          }
        }

        if (data.status === 'done') {
          clearInterval(pollTimer);
          runBtn.disabled = false;
          runLabel.textContent = 'Run generator';
          runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>';
          showProgress(false);
          resultError.classList.add('hidden');
          resultBody.innerHTML = statCard('Ads generated', data.result.num_ads) +
            statCard('Accepted (≥' + (data.result.quality_threshold || '7.0') + ')', data.result.accepted) +
            statCard('Average score', data.result.avg_score) +
            (data.result.backend ? statCard('Model', data.result.backend + ' (generation + evaluation)') : '') +
            (data.result.total_tokens != null ? statCard('Total tokens', data.result.total_tokens.toLocaleString()) : '') +
            (data.result.estimated_cost_usd != null ? statCard('Est. cost', '$' + data.result.estimated_cost_usd) : '') +
            (data.result.roi_accepted_per_1k_tokens != null ? statCard('ROI (accepted/1K tok)', data.result.roi_accepted_per_1k_tokens) : '') +
            statCard('Output', '<span class="text-sm font-mono text-slate-600 truncate block" title="' + data.result.output_dir + '">' + data.result.output_dir.replace(/.*[/\\\\]/, '') + '</span>');
          showResult(true);
          if (data.completed_ads && data.completed_ads.length > 0) {
            allCompletedAds = data.completed_ads;
            renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
            showGeneratedAds(true);
          }
          fetchOutputs();
          fetchResultViews();
          showAdLibrary();
        } else if (data.status === 'error') {
          clearInterval(pollTimer);
          runBtn.disabled = false;
          runLabel.textContent = 'Run generator';
          runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>';
          showProgress(false);
          resultBody.innerHTML = '';
          resultError.textContent = data.error || 'Unknown error';
          resultError.classList.remove('hidden');
          showResult(true);
        }
      });
    }

    function fetchOutputs() {
      fetch('/api/outputs').then(r => r.json()).then(data => {
        const files = data.files || [];
        const runId = data.run_id;
        const runTs = data.run_timestamp;
        const runInfoEl = document.getElementById('outputsRunInfo');
        if (runInfoEl) {
          if (runId && runTs) {
            try {
              const d = new Date(runTs);
              const dateStr = isNaN(d.getTime()) ? runTs.slice(0, 19) : (d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) + ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }));
              runInfoEl.textContent = 'Current run: ' + dateStr + ' — ' + runId;
            } catch (e) {
              runInfoEl.textContent = 'Current run: ' + runId;
            }
          } else {
            runInfoEl.textContent = 'Click any file to preview, or download directly.';
          }
        }
        var fileIconMap = {
          'ads_dataset.json': '<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>',
          'evaluation_report.csv': '<svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>',
          'evaluation_summary.txt': '<svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>',
          'iteration_quality_chart.png': '<svg class="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>'
        };
        outputList.innerHTML = files.map(function(f) {
          var size = f.size ? (Math.round(f.size / 1024) + ' KB') : '';
          var desc = (f.description || '').trim();
          var icon = fileIconMap[f.name] || fileIconMap['evaluation_summary.txt'];
          return '<div class="output-file-item">' +
            '<div class="px-6 py-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50/80 transition-colors output-file-header" data-filename="' + esc(f.name) + '">' +
              '<div class="shrink-0">' + icon + '</div>' +
              '<div class="flex-1 min-w-0">' +
                '<p class="font-medium text-slate-900 text-sm">' + esc(f.name) + '</p>' +
                (desc ? '<p class="text-xs text-slate-500 mt-0.5">' + esc(desc) + '</p>' : '') +
              '</div>' +
              '<div class="flex items-center gap-3 shrink-0">' +
                '<span class="text-xs text-slate-400">' + size + '</span>' +
                '<a href="/api/output/' + esc(f.name) + '" download class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary-50 text-primary-700 text-xs font-medium hover:bg-primary-100 transition-colors" onclick="event.stopPropagation()">' +
                  '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>' +
                  'Download' +
                '</a>' +
                '<svg class="w-4 h-4 text-slate-400 output-chevron transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>' +
              '</div>' +
            '</div>' +
            '<div class="output-file-preview hidden px-6 pb-4" data-preview-for="' + esc(f.name) + '"></div>' +
          '</div>';
        }).join('');
        showOutputs(files.length > 0);
        // Attach expand/collapse handlers
        outputList.querySelectorAll('.output-file-header').forEach(function(header) {
          header.addEventListener('click', function() {
            var fname = header.getAttribute('data-filename');
            var preview = outputList.querySelector('[data-preview-for="' + fname + '"]');
            var chevron = header.querySelector('.output-chevron');
            if (!preview) return;
            if (!preview.classList.contains('hidden')) {
              preview.classList.add('hidden');
              if (chevron) chevron.style.transform = '';
              return;
            }
            preview.classList.remove('hidden');
            if (chevron) chevron.style.transform = 'rotate(180deg)';
            if (preview.getAttribute('data-loaded')) return;
            preview.innerHTML = '<div class="flex items-center gap-2 py-3"><svg class="w-4 h-4 text-slate-400 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg><span class="text-sm text-slate-500">Loading preview...</span></div>';
            loadOutputPreview(fname, preview);
          });
        });
      });
    }
    function loadOutputPreview(fname, container) {
      if (fname.endsWith('.png')) {
        container.innerHTML = '<img src="/api/output/' + esc(fname) + '?inline=1&t=' + Date.now() + '" alt="' + esc(fname) + '" class="max-w-full h-auto rounded-lg border border-slate-200">';
        container.setAttribute('data-loaded', '1');
        return;
      }
      if (fname.endsWith('.txt')) {
        fetch('/api/result/summary').then(function(r) { return r.ok ? r.text() : 'Could not load file'; }).then(function(text) {
          container.innerHTML = '<pre class="bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs text-slate-700 whitespace-pre-wrap max-h-80 overflow-y-auto font-mono">' + esc(text) + '</pre>';
          container.setAttribute('data-loaded', '1');
        });
        return;
      }
      if (fname.endsWith('.json')) {
        fetch('/api/result/ads_dataset').then(function(r) { return r.json(); }).then(function(data) {
          var pretty = JSON.stringify(data, null, 2);
          if (pretty.length > 10000) pretty = pretty.slice(0, 10000) + '\\n\\n... (truncated)';
          container.innerHTML = '<pre class="bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs text-slate-700 whitespace-pre-wrap max-h-96 overflow-y-auto font-mono">' + esc(pretty) + '</pre>';
          container.setAttribute('data-loaded', '1');
        });
        return;
      }
      if (fname.endsWith('.csv')) {
        fetch('/api/result/evaluation_report').then(function(r) { return r.json(); }).then(function(rows) {
          if (!rows || !rows.length) { container.innerHTML = '<p class="text-sm text-slate-500 py-2">Empty file</p>'; container.setAttribute('data-loaded', '1'); return; }
          var cols = Object.keys(rows[0]);
          container.innerHTML = '<div class="overflow-x-auto max-h-80"><table class="w-full text-xs text-left border-collapse">' +
            '<thead class="bg-slate-100 sticky top-0"><tr>' + cols.map(function(c) { return '<th class="px-3 py-2 font-semibold text-slate-600 border-b border-slate-200">' + esc(c) + '</th>'; }).join('') + '</tr></thead>' +
            '<tbody>' + rows.map(function(row, i) { return '<tr class="' + (i % 2 ? 'bg-slate-50/50' : '') + '">' + cols.map(function(c) { return '<td class="px-3 py-1.5 text-slate-700 border-b border-slate-100">' + esc(String(row[c] != null ? row[c] : '')) + '</td>'; }).join('') + '</tr>'; }).join('') +
            '</tbody></table></div>';
          container.setAttribute('data-loaded', '1');
        });
        return;
      }
      container.innerHTML = '<p class="text-sm text-slate-500 py-2">Preview not available for this file type.</p>';
      container.setAttribute('data-loaded', '1');
    }

    function showEl(id, show) {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('hidden', !show);
    }

    // --- Dynamic quality trend chart (canvas) — updates after each improvement ---
    var _chartHistory = []; // [{label, avgScore}]
    function drawQualityChart(ads) {
      var canvas = document.getElementById('qualityChart');
      var card = document.getElementById('chartCard');
      if (!canvas || !card) return;
      if (!ads || ads.length === 0) { showEl('chartCard', false); return; }
      // Compute current average score
      var total = 0; var count = 0;
      ads.forEach(function(a) {
        var s = parseFloat(a.overall_score);
        if (!isNaN(s)) { total += s; count++; }
      });
      if (count === 0) { showEl('chartCard', false); return; }
      var avg = total / count;
      // Add to history if this is a new point (different from last)
      if (_chartHistory.length === 0) {
        _chartHistory.push({ label: 'Initial', avgScore: avg });
      } else {
        var last = _chartHistory[_chartHistory.length - 1];
        if (Math.abs(last.avgScore - avg) > 0.005) {
          _chartHistory.push({ label: 'Cycle ' + _chartHistory.length, avgScore: avg });
        }
      }
      showEl('chartCard', true);
      // Draw on canvas
      var ctx = canvas.getContext('2d');
      var W = canvas.width, H = canvas.height;
      var pad = { top: 30, right: 30, bottom: 40, left: 55 };
      ctx.clearRect(0, 0, W, H);
      // Y-axis range
      var allScores = _chartHistory.map(function(p) { return p.avgScore; });
      var minY = Math.min(Math.min.apply(null, allScores), 7.0) - 0.3;
      var maxY = Math.max(Math.max.apply(null, allScores), 7.0) + 0.5;
      var chartW = W - pad.left - pad.right;
      var chartH = H - pad.top - pad.bottom;
      function toX(i) { return pad.left + (allScores.length > 1 ? (i / (allScores.length - 1)) * chartW : chartW / 2); }
      function toY(v) { return pad.top + chartH - ((v - minY) / (maxY - minY)) * chartH; }
      // Grid lines
      ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
      for (var g = Math.ceil(minY * 2) / 2; g <= maxY; g += 0.5) {
        var gy = toY(g);
        ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(W - pad.right, gy); ctx.stroke();
        ctx.fillStyle = '#94a3b8'; ctx.font = '11px system-ui'; ctx.textAlign = 'right';
        ctx.fillText(g.toFixed(1), pad.left - 8, gy + 4);
      }
      // Threshold line at 7.0
      var thY = toY(7.0);
      ctx.setLineDash([6, 4]); ctx.strokeStyle = '#ef4444'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(pad.left, thY); ctx.lineTo(W - pad.right, thY); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#ef4444'; ctx.font = 'bold 10px system-ui'; ctx.textAlign = 'left';
      ctx.fillText('Threshold 7.0', W - pad.right - 75, thY - 6);
      // Line + points
      if (allScores.length > 1) {
        ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 2.5;
        ctx.beginPath();
        allScores.forEach(function(v, i) {
          if (i === 0) ctx.moveTo(toX(i), toY(v));
          else ctx.lineTo(toX(i), toY(v));
        });
        ctx.stroke();
      }
      // Points + labels
      allScores.forEach(function(v, i) {
        ctx.beginPath(); ctx.arc(toX(i), toY(v), 5, 0, Math.PI * 2);
        ctx.fillStyle = '#3b82f6'; ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
        ctx.fillStyle = '#1e40af'; ctx.font = 'bold 11px system-ui'; ctx.textAlign = 'center';
        ctx.fillText(v.toFixed(2), toX(i), toY(v) - 12);
      });
      // X-axis labels
      ctx.fillStyle = '#64748b'; ctx.font = '11px system-ui'; ctx.textAlign = 'center';
      _chartHistory.forEach(function(p, i) {
        ctx.fillText(p.label, toX(i), H - pad.bottom + 20);
      });
      // Title
      ctx.fillStyle = '#334155'; ctx.font = 'bold 13px system-ui'; ctx.textAlign = 'center';
      ctx.fillText('Average quality score over iterations', W / 2, 18);
    }

    function fetchResultViews() {
      fetch('/api/result/ads_dataset').then(r => r.json()).then(function(ads) {
        if (ads && ads.length > 0) {
          allCompletedAds = ads;
          renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
          if (generatedAdsCard) generatedAdsCard.classList.remove('hidden');
        }
      }).catch(function() {});
      fetch('/api/result/summary').then(function(r) {
        if (r.ok) return r.text();
        return null;
      }).then(function(text) {
        const summaryText = document.getElementById('summaryText');
        const summaryCard = document.getElementById('summaryCard');
        if (summaryText && summaryCard) {
          summaryText.textContent = text || '';
          showEl('summaryCard', !!text);
        }
      }).catch(function() {});
      drawQualityChart(allCompletedAds);
      fetch('/api/result/evaluation_report').then(r => r.json()).then(function(rows) {
        const table = document.getElementById('scoresTable');
        const card = document.getElementById('scoresTableCard');
        if (!table || !card) return;
        if (!rows || rows.length === 0) { showEl('scoresTableCard', false); return; }
        const cols = Object.keys(rows[0]);
        table.innerHTML = '<thead class="bg-slate-50 border-b border-slate-200"><tr>' +
          cols.map(function(c) { return '<th class="px-4 py-2 text-left text-xs font-semibold text-slate-600">' + esc(c) + '</th>'; }).join('') +
          '</tr></thead><tbody>' +
          rows.map(function(row, i) {
            return '<tr class="border-b border-slate-100 ' + (i % 2 ? 'bg-slate-50/50' : '') + '">' +
              cols.map(function(c) { return '<td class="px-4 py-2 text-sm text-slate-700">' + esc(String(row[c] != null ? row[c] : '')) + '</td>'; }).join('') +
              '</tr>';
          }).join('') + '</tbody>';
        showEl('scoresTableCard', true);
      }).catch(function() {});
    }

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      const api_key = (document.getElementById('api_key') && document.getElementById('api_key').value) ? document.getElementById('api_key').value.trim() : '';
      const openai_api_key = (document.getElementById('openai_api_key') && document.getElementById('openai_api_key').value) ? document.getElementById('openai_api_key').value.trim() : '';
      const openrouter_api_key = (document.getElementById('openrouter_api_key') && document.getElementById('openrouter_api_key').value) ? document.getElementById('openrouter_api_key').value.trim() : '';
      const openrouter_model = (document.getElementById('openrouter_model') && document.getElementById('openrouter_model').value) ? document.getElementById('openrouter_model').value.trim() : 'google/gemini-2.0-flash-001';
      const num_ads = parseInt(document.getElementById('num_ads').value, 10) || 5;
      const max_iterations = parseInt(document.getElementById('max_iterations').value, 10) || 1;
      const seed = parseInt(document.getElementById('seed').value, 10) || 42;
      const brand_name = (document.getElementById('brand_name') && document.getElementById('brand_name').value) ? document.getElementById('brand_name').value.trim() : '';
      const audience = (document.getElementById('audience') && document.getElementById('audience').value) ? document.getElementById('audience').value.trim() : '';
      const product = (document.getElementById('product') && document.getElementById('product').value) ? document.getElementById('product').value.trim() : '';
      const goal = (document.getElementById('goal') && document.getElementById('goal').value) ? document.getElementById('goal').value.trim() : '';
      const tone = (document.getElementById('tone') && document.getElementById('tone').value) ? document.getElementById('tone').value.trim() : '';
      const qualityThresholdEl = document.getElementById('quality_threshold');
      const quality_threshold = qualityThresholdEl && qualityThresholdEl.value ? parseFloat(qualityThresholdEl.value) : undefined;
      const enable_image_gen = !!(document.getElementById('enable_image_gen') && document.getElementById('enable_image_gen').checked);
      const additional_context_el = document.getElementById('additional_context');
      const additional_context = additional_context_el ? additional_context_el.value.trim() : '';
      if (!brand_name || !audience || !product || !goal) { alert('Please fill in all required fields: Brand name, Audience, Product, and Goal.'); return; }
      runBtn.disabled = true;
      runLabel.textContent = 'Running…';
      runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>';
      showProgress(true);
      showResult(false);
      allCompletedAds = [];
      currentPage = 1;
      showGeneratedAds(false);
      showEl('summaryCard', false);
      showEl('chartCard', false);
      showEl('scoresTableCard', false);
      fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: api_key || undefined, openai_api_key: openai_api_key || undefined, openrouter_api_key: openrouter_api_key || undefined, openrouter_model: openrouter_model || undefined, num_ads, max_iterations, seed, quality_threshold: quality_threshold || undefined, enable_image_gen, brand_name: brand_name || undefined, audience: audience || undefined, product: product || undefined, goal: goal || undefined, tone: tone || undefined, additional_context: additional_context || undefined })
      }).then(r => r.json()).then(data => {
        if (data.ok) pollTimer = setInterval(poll, 300);
        else { runBtn.disabled = false; runLabel.textContent = 'Run generator'; runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>'; showProgress(false); alert(data.error || 'Failed to start'); }
      }).catch(function() {
        runBtn.disabled = false;
        runLabel.textContent = 'Run generator';
        runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>';
        showProgress(false);
        alert('Request failed');
      });
    });

    if (paginationPrev) paginationPrev.addEventListener('click', function() {
      if (currentPage <= 1) return;
      currentPage--;
      renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
    });
    if (paginationNext) paginationNext.addEventListener('click', function() {
      const totalPages = Math.ceil((allCompletedAds.length || 0) / PAGE_SIZE);
      if (currentPage >= totalPages) return;
      currentPage++;
      renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
    });

    // Inline improve popover — shows a small dropdown below the "Make it better" button
    var _activePopover = null;
    function closeImprovePopover() {
      if (_activePopover) { _activePopover.remove(); _activePopover = null; }
      document.removeEventListener('click', _popoverOutsideClick, true);
    }
    function _popoverOutsideClick(e) {
      if (_activePopover && !_activePopover.contains(e.target) && !e.target.closest('.improve-ad-btn')) {
        closeImprovePopover();
      }
    }
    if (generatedAdsList) generatedAdsList.addEventListener('click', function(e) {
      var btn = e.target && e.target.closest && e.target.closest('.improve-ad-btn');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      var adId = btn.getAttribute('data-ad-id');
      if (!adId) return;
      // If popover already open for this ad, close it
      if (_activePopover && _activePopover.dataset.adId === adId) { closeImprovePopover(); return; }
      closeImprovePopover();
      // Create inline popover
      var pop = document.createElement('div');
      pop.dataset.adId = adId;
      pop.className = 'absolute z-40 mt-2 right-0 w-80 bg-white rounded-xl shadow-xl border border-slate-200 p-4';
      pop.innerHTML =
        '<label class="block text-xs font-semibold text-slate-700 mb-1">Additional context <span class="font-normal text-slate-400">(optional)</span></label>' +
        '<textarea class="improve-popover-text block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm resize-none" rows="2" placeholder="e.g. punchier headline, more urgency..."></textarea>' +
        '<button type="button" class="improve-popover-go mt-2 w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white font-semibold rounded-lg shadow-sm hover:bg-primary-700 text-xs transition-colors">' +
          '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>' +
          'Improve this ad</button>';
      // Position relative to button
      var wrapper = btn.parentElement;
      if (wrapper) { wrapper.style.position = 'relative'; wrapper.appendChild(pop); }
      _activePopover = pop;
      setTimeout(function() { document.addEventListener('click', _popoverOutsideClick, true); }, 0);
      // Handle submit
      pop.querySelector('.improve-popover-go').addEventListener('click', function() {
        var userContext = (pop.querySelector('.improve-popover-text').value || '').trim();
        closeImprovePopover();
      // Now show the loading skeleton and fire the improve request
      var currentAd = allCompletedAds.find(function(a) { return (a.id || a.ad_id) === adId; });
      var currentCycle = (currentAd && currentAd.iteration_count) ? currentAd.iteration_count : 1;
      var nextCycle = currentCycle + 1;
      var cardWrapper = document.getElementById('ad-card-' + adId);
      if (cardWrapper) {
        var startTime = Date.now();
        cardWrapper.innerHTML =
          '<div class="rounded-xl border border-primary-200 bg-primary-50/30 shadow-sm p-6 text-center">' +
            '<div class="flex items-center justify-center gap-3 mb-4">' +
              '<svg class="w-6 h-6 text-primary-500 spin-slow" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>' +
              '<span class="text-sm font-semibold text-primary-700">Improving ad — iteration ' + nextCycle + '</span>' +
            '</div>' +
            '<div class="space-y-3">' +
              '<div class="h-3 bg-primary-100 rounded-full w-3/4 mx-auto progress-indeterminate"></div>' +
              '<div class="h-3 bg-primary-100 rounded-full w-1/2 mx-auto progress-indeterminate" style="animation-delay:0.2s"></div>' +
              '<div class="h-3 bg-primary-100 rounded-full w-2/3 mx-auto progress-indeterminate" style="animation-delay:0.4s"></div>' +
            '</div>' +
            '<div class="mt-4 flex items-center justify-center gap-4 text-xs text-slate-500">' +
              '<span>Cycle <strong class="text-primary-700">' + currentCycle + ' → ' + nextCycle + '</strong></span>' +
              '<span id="improve-timer-' + adId + '">0s</span>' +
            '</div>' +
            (userContext ? '<p class="text-xs text-primary-600 mt-2 italic truncate max-w-xs mx-auto">With context: ' + esc(userContext.slice(0, 80)) + (userContext.length > 80 ? '...' : '') + '</p>' : '') +
            '<p class="text-xs text-slate-400 mt-1">Evaluating weakest dimension, generating improved copy, re-scoring...</p>' +
          '</div>';
        var timerEl = document.getElementById('improve-timer-' + adId);
        var timerInterval = setInterval(function() {
          if (!timerEl) { clearInterval(timerInterval); return; }
          var elapsed = Math.round((Date.now() - startTime) / 1000);
          timerEl.textContent = elapsed + 's';
        }, 1000);
      }
      var qtEl = document.getElementById('quality_threshold');
      var qt = qtEl && qtEl.value ? parseFloat(qtEl.value) : undefined;
      fetch('/api/improve_ad', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ad_id: adId, quality_threshold: qt, user_context: userContext || undefined }) })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok && data.ad) {
            var idx = allCompletedAds.findIndex(function(a) { return (a.id || a.ad_id) === adId; });
            if (idx >= 0) { allCompletedAds[idx] = data.ad; }
            renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
            drawQualityChart(allCompletedAds);
          } else {
            alert(data.error || 'Improve failed');
            renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
          }
        })
        .catch(function() {
          alert('Request failed — check server logs');
          renderGeneratedAdsPage(allCompletedAds, currentPage, PAGE_SIZE);
        });
      }); // end popover go click
    }); // end generatedAdsList click

    // --- Facebook Ad Library: show related ads after generation ---
    function showAdLibrary() {
      var card = document.getElementById('adLibraryCard');
      var linksEl = document.getElementById('adLibraryLinks');
      if (!card || !linksEl) return;
      var brandEl = document.getElementById('brand_name');
      var productEl = document.getElementById('product');
      var audienceEl = document.getElementById('audience');
      var brand = brandEl ? brandEl.value.trim() : '';
      var product = productEl ? productEl.value.trim() : '';
      var audience = audienceEl ? audienceEl.value.trim() : '';
      if (!brand && !product) return;
      // Extract the core product category (last meaningful word)
      var productWords = (product || '').replace(/[^a-zA-Z0-9 ]/g, '').split(/\s+/).filter(function(w) { return w.length > 2; });
      var coreProduct = productWords.length > 0 ? productWords[productWords.length - 1] : '';
      var searches = [];
      // 1. Brand name — searches by advertiser/page name (most reliable)
      if (brand) searches.push({ label: brand, query: brand, desc: 'Ads by this brand' });
      // 2. Core product category — broader search that actually returns results
      if (coreProduct && coreProduct.toLowerCase() !== brand.toLowerCase()) {
        searches.push({ label: coreProduct, query: coreProduct, desc: 'Ads in this category' });
      }
      // 3. Brand + core product — targeted cross-reference
      if (brand && coreProduct) searches.push({ label: brand + ' ' + coreProduct, query: brand + ' ' + coreProduct, desc: 'Brand + category' });
      // 4. Full product if different from core — user's exact terms
      if (product && product.toLowerCase() !== coreProduct.toLowerCase() && product.toLowerCase() !== brand.toLowerCase()) {
        searches.push({ label: product, query: product, desc: 'Exact product match' });
      }
      linksEl.innerHTML = searches.map(function(s) {
        var url = 'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=' + encodeURIComponent(s.query);
        return '<a href="' + esc(url) + '" target="_blank" rel="noopener" class="flex items-center gap-3 p-3 rounded-xl border border-slate-200 hover:border-blue-300 hover:bg-blue-50/50 transition-colors group">' +
          '<div class="shrink-0 w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center">' +
            '<svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>' +
          '</div>' +
          '<div class="min-w-0 flex-1">' +
            '<p class="text-sm font-medium text-slate-800 group-hover:text-blue-700 truncate">' + esc(s.label) + '</p>' +
            '<p class="text-xs text-slate-400">' + esc(s.desc || 'Active ads on Meta') + '</p>' +
          '</div>' +
          '<svg class="w-4 h-4 text-slate-300 group-hover:text-blue-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>' +
        '</a>';
      }).join('');
      card.classList.remove('hidden');
    }
    fetchOutputs();
    fetchResultViews();
  </script>
</body>
</html>
"""


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ROI Dashboard — Facebook Ad Engine</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = { theme: { extend: { fontFamily: { sans: ['DM Sans', 'sans-serif'] }, colors: { primary: { 500: '#10b981', 600: '#059669' } } } } }
  </script>
</head>
<body class="min-h-screen bg-slate-50 text-slate-800 font-sans antialiased">
  <header class="border-b border-slate-200/80 bg-white/90 backdrop-blur-sm sticky top-0 z-10">
    <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-xl font-bold tracking-tight text-slate-900">Facebook</span>
        <span class="text-xl font-semibold text-primary-600">Ad Engine</span>
      </div>
      <nav class="flex items-center gap-1">
        <a href="/" class="px-3 py-1.5 text-sm font-medium rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-800 transition-colors">Generator</a>
        <a href="/dashboard" class="px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-50 text-primary-700">Campaigns</a>
        <span class="px-3 py-1.5 text-sm font-medium rounded-lg text-slate-400 cursor-not-allowed select-none" title="Coming soon">Studio <span class="text-[10px] bg-slate-100 text-slate-400 px-1.5 py-0.5 rounded-md ml-0.5 uppercase tracking-wider">TBA</span></span>
      </nav>
    </div>
  </header>
  <main class="max-w-6xl mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold text-slate-900 mb-1">Campaigns</h1>
    <p class="text-slate-500 text-sm mb-6">Browse past runs, compare performance, and iterate on campaigns.</p>

    <!-- Aggregate stats (filled by JS) -->
    <div id="aggStats" class="hidden grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide">Campaigns</p>
        <p id="aggCampaigns" class="text-2xl font-bold text-slate-900 mt-1">0</p>
      </div>
      <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide">Total Ads</p>
        <p id="aggAds" class="text-2xl font-bold text-slate-900 mt-1">0</p>
      </div>
      <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide">Avg Score</p>
        <p id="aggScore" class="text-2xl font-bold text-primary-600 mt-1">—</p>
      </div>
      <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide">Acceptance Rate</p>
        <p id="aggAccept" class="text-2xl font-bold text-emerald-600 mt-1">—</p>
      </div>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div class="flex items-center gap-3">
        <label class="text-sm font-medium text-slate-600">Sort by</label>
        <select id="sortBy" class="rounded-lg border border-slate-300 text-sm px-3 py-1.5">
          <option value="date_desc">Newest first</option>
          <option value="date_asc">Oldest first</option>
          <option value="accepted_desc">Most accepted</option>
          <option value="score_desc">Highest score</option>
          <option value="tokens_desc">Most tokens</option>
        </select>
      </div>
      <details class="text-sm" id="glossary">
        <summary class="cursor-pointer text-slate-500 hover:text-slate-700 select-none">Glossary</summary>
        <div class="absolute right-4 mt-1 bg-white rounded-lg border border-slate-200 shadow-lg p-4 text-xs text-slate-600 space-y-1 max-w-xs z-10">
          <p><strong>Tokens</strong> — Text units the AI reads/writes (~4 chars each).</p>
          <p><strong>Quality bar</strong> — 7.0/10. Ads at or above are accepted.</p>
          <p><strong>Points</strong> — Quality per dollar (avg score / cost).</p>
        </div>
      </details>
    </div>

    <div id="runSummaries"></div>
    <p id="noRuns" class="hidden py-8 text-slate-500 text-center">No runs yet. Generate ads from the Generator page to see campaigns here.</p>

    <div id="drillDown" class="hidden fixed inset-0 z-20 bg-slate-900/50 flex items-center justify-center p-4">
      <div class="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div class="px-4 py-3 border-b flex items-center justify-between">
          <h2 id="drillTitle" class="font-semibold text-slate-900">Campaign ads</h2>
          <button type="button" id="drillClose" class="text-slate-500 hover:text-slate-800">Close</button>
        </div>
        <div id="drillBody" class="p-4 overflow-y-auto flex-1 text-sm"></div>
      </div>
    </div>
  </main>

  <script>
    var allRuns = [];

    function summaryText(r) {
      const numAds = r.num_ads || 0;
      const accepted = r.accepted ?? 0;
      const avgScore = r.avg_score != null ? r.avg_score : null;
      const tokens = r.total_tokens != null ? r.total_tokens : null;
      const cost = r.estimated_cost_usd != null ? r.estimated_cost_usd : null;
      const pctAccepted = numAds > 0 ? Math.round((accepted / numAds) * 100) : 0;
      return '<div class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600">' +
        '<span><strong class="text-slate-900">' + numAds + '</strong> ads</span>' +
        '<span><strong class="text-emerald-700">' + accepted + '</strong> accepted (' + pctAccepted + '%)</span>' +
        (avgScore != null ? '<span>Score: <strong class="' + (avgScore >= 8 ? 'text-emerald-700' : avgScore >= 7 ? 'text-primary-700' : 'text-amber-600') + '">' + avgScore + '</strong>/10</span>' : '') +
        (tokens != null ? '<span>' + (tokens >= 1000 ? (tokens / 1000).toFixed(1) + 'K' : tokens) + ' tokens</span>' : '') +
        (cost != null && cost > 0 ? '<span>$' + cost.toFixed(4) + '</span>' : '') +
        '</div>';
    }

    function sortRuns(runs, key) {
      var list = runs.slice();
      if (key === 'date_desc') list.reverse();
      else if (key === 'date_asc') { }
      else if (key === 'accepted_desc') list.sort(function(a,b) { return (b.accepted || 0) - (a.accepted || 0); });
      else if (key === 'score_desc') list.sort(function(a,b) { return (b.avg_score || 0) - (a.avg_score || 0); });
      else if (key === 'tokens_desc') list.sort(function(a,b) { return (b.total_tokens || 0) - (a.total_tokens || 0); });
      return list;
    }

    function renderCampaigns(runs) {
      const container = document.getElementById('runSummaries');
      const sortKey = (document.getElementById('sortBy') && document.getElementById('sortBy').value) || 'date_desc';
      const sorted = sortRuns(runs, sortKey);
      container.innerHTML = sorted.map(function(r) {
        const runId = r.run_id || (r.timestamp || '').replace(/[-:Z.]/g, '').slice(0, 15);
        const time = (r.timestamp || '').replace('T', ' ').slice(0, 19).replace(/-/g, '/');
        const name = (r.name || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const outputs = r.outputs || [];
        const downloadsHtml = outputs.length ? (
          '<div class="mt-2 pt-2 border-t border-slate-100">' +
            '<p class="text-xs font-medium text-slate-500 mb-1">Downloads</p>' +
            '<div class="flex flex-wrap gap-x-3 gap-y-1 text-xs">' +
              outputs.map(function(f) {
                const sz = f.size != null ? (Math.round(f.size / 1024) + ' KB') : '';
                return '<a href="/api/runs/' + encodeURIComponent(runId) + '/output/' + encodeURIComponent(f.name) + '" download class="text-primary-600 hover:underline">' + f.name + (sz ? ' (' + sz + ')' : '') + '</a>';
              }).join('') +
            '</div>' +
          '</div>'
        ) : '';
        return '<div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm mb-4" data-run-id="' + runId + '">' +
          '<div class="flex flex-wrap items-start justify-between gap-2 mb-2">' +
            '<div class="flex-1 min-w-0">' +
              '<input type="text" class="campaign-name text-sm font-medium text-slate-800 border-0 border-b border-transparent hover:border-slate-300 focus:border-primary-500 focus:ring-0 bg-transparent w-full max-w-md" value="' + name + '" placeholder="Name this campaign" data-run-id="' + runId + '" />' +
              '<p class="text-slate-500 text-xs mt-0.5">' + time + (r.backend ? ' · ' + r.backend : '') + '</p>' +
            '</div>' +
            '<button type="button" class="view-ads px-3 py-1.5 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg" data-run-id="' + runId + '">View ads</button>' +
            '<button type="button" class="improve-again px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg border border-slate-200" data-run-id="' + runId + '">Improve again</button>' +
          '</div>' +
          '<p class="text-slate-800 leading-relaxed">' + summaryText(r) + '</p>' +
          downloadsHtml +
          '</div>';
      }).join('');

      document.querySelectorAll('.campaign-name').forEach(function(inp) {
        inp.addEventListener('blur', function() {
          const id = this.getAttribute('data-run-id');
          const name = this.value.trim();
          fetch('/api/campaign_name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: id, name: name }) }).then(function() {
            var run = allRuns.find(function(r) { return (r.run_id || '').replace(/[-:Z.]/g,'').slice(0,15) === id || r.run_id === id; });
            if (run) run.name = name;
          });
        });
      });
      document.querySelectorAll('.view-ads').forEach(function(btn) {
        btn.addEventListener('click', function() {
          const runId = this.getAttribute('data-run-id');
          const run = allRuns.find(function(r) { return (r.run_id || '').replace(/[-:Z.]/g,'').slice(0,15) === runId || r.run_id === runId; });
          const title = (run && run.name) ? run.name : ('Run ' + runId);
          document.getElementById('drillTitle').textContent = title;
          document.getElementById('drillDown').classList.remove('hidden');
          document.getElementById('drillBody').innerHTML = '<p class="text-slate-500">Loading…</p>';
          fetch('/api/runs/' + encodeURIComponent(runId) + '/ads').then(function(res) { return res.json(); }).then(function(ads) {
            if (!ads || ads.length === 0) {
              document.getElementById('drillBody').innerHTML = '<p class="text-slate-500">No ad data for this run. Per-run ads are saved for runs after the dashboard update.</p>';
              return;
            }
            var html = '<table class="w-full border border-slate-200"><thead><tr class="bg-slate-50 text-left text-slate-600 font-medium"><th class="px-3 py-2 border-b">Ad</th><th class="px-3 py-2 border-b">Headline</th><th class="px-3 py-2 border-b">Score</th><th class="px-3 py-2 border-b">Accepted</th><th class="px-3 py-2 border-b">Iterations</th></tr></thead><tbody>';
            ads.forEach(function(ad) {
              const copy = ad.ad_copy || {};
              const headline = (copy.headline || copy.primary_text || '—').slice(0, 60);
              const score = ad.overall_score != null ? ad.overall_score : '—';
              const acc = ad.accepted ? 'Yes' : 'No';
              const iter = ad.iteration_count != null ? ad.iteration_count : '—';
              html += '<tr class="border-t border-slate-100"><td class="px-3 py-2 font-mono text-xs">' + (ad.id || '—') + '</td><td class="px-3 py-2">' + headline + '</td><td class="px-3 py-2">' + score + '</td><td class="px-3 py-2">' + acc + '</td><td class="px-3 py-2">' + iter + '</td></tr>';
            });
            html += '</tbody></table>';
            document.getElementById('drillBody').innerHTML = html;
          }).catch(function() {
            document.getElementById('drillBody').innerHTML = '<p class="text-red-600">Failed to load ads.</p>';
          });
        });
      });
      document.querySelectorAll('.improve-again').forEach(function(btn) {
        btn.addEventListener('click', function() {
          var runId = btn.getAttribute('data-run-id');
          if (!runId) return;
          btn.disabled = true;
          fetch('/api/iterate_campaign', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId, max_extra_iterations: 3 }) }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.ok) { btn.disabled = false; alert(data.error || 'Failed'); return; }
            var iv = setInterval(function() {
              fetch('/api/status').then(function(r) { return r.json(); }).then(function(s) {
                if (s.status === 'done' && s.result) { clearInterval(iv); btn.disabled = false; alert('Done. Refresh to see new campaign.'); fetch('/api/run_history').then(function(r) { return r.json(); }).then(function(runs) { allRuns = runs || []; renderCampaigns(allRuns); }); }
                else if (s.status === 'error') { clearInterval(iv); btn.disabled = false; alert('Error: ' + (s.error || '')); }
              });
            }, 1500);
          }).catch(function() { btn.disabled = false; alert('Request failed'); });
        });
      });
    }

    document.getElementById('sortBy').addEventListener('change', function() { renderCampaigns(allRuns); });
    document.getElementById('drillClose').addEventListener('click', function() { document.getElementById('drillDown').classList.add('hidden'); });

    function updateAggStats(runs) {
      if (!runs || runs.length === 0) return;
      var totalAds = 0, totalAccepted = 0, scoreSum = 0, scoreCount = 0;
      runs.forEach(function(r) {
        totalAds += (r.num_ads || 0);
        totalAccepted += (r.accepted || 0);
        if (r.avg_score != null) { scoreSum += r.avg_score; scoreCount++; }
      });
      var el = document.getElementById('aggStats');
      if (el) el.classList.remove('hidden');
      var c = document.getElementById('aggCampaigns'); if (c) c.textContent = runs.length;
      var a = document.getElementById('aggAds'); if (a) a.textContent = totalAds;
      var s = document.getElementById('aggScore'); if (s) s.textContent = scoreCount > 0 ? (scoreSum / scoreCount).toFixed(2) : '—';
      var acc = document.getElementById('aggAccept'); if (acc) acc.textContent = totalAds > 0 ? Math.round((totalAccepted / totalAds) * 100) + '%' : '—';
    }

    fetch('/api/run_history').then(r => r.json()).then(function(runs) {
      const container = document.getElementById('runSummaries');
      const noRuns = document.getElementById('noRuns');

      if (!runs || runs.length === 0) {
        noRuns.classList.remove('hidden');
        return;
      }
      allRuns = runs;
      updateAggStats(runs);
      renderCampaigns(runs);
    });
  </script>
</body>
</html>
"""


def main():
    port = int(os.environ.get("PORT", 8080))
    for attempt in range(10):
        try:
            app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
            return
        except OSError as e:
            if "Address already in use" in str(e) or (hasattr(e, "errno") and e.errno == 48):
                print("Port %d in use, trying %d..." % (port, port + 1), file=__import__("sys").stderr)
                port += 1
            else:
                raise
    print("Could not bind to any port between %d and %d." % (port - 10, port), file=__import__("sys").stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
