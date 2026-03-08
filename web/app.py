"""Web interface for Nerdy Autonomous Ad Engine."""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request, send_from_directory

# Load .env from project root so OPENROUTER_API_KEY etc. are available
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add project root for ad_engine imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from ad_engine.cli import run_pipeline

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

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
    max_iterations = min(max(1, int(data.get("max_iterations", 6))), 10)
    seed = int(data.get("seed", 42))
    output_dir = str(ROOT / "output")

    # Optional: set API keys from request (not persisted; used only for this process)
    api_key = (data.get("api_key") or "").strip()
    openrouter_key = (data.get("openrouter_api_key") or "").strip()
    openrouter_model = (data.get("openrouter_model") or "").strip() or "openrouter/free"
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    # Only override OpenRouter from form when user actually entered a key (full key in .env used when blank)
    if openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
        os.environ["OPENROUTER_MODEL"] = openrouter_model
    # Fallback order: Gemini first, then OpenRouter, then OpenAI (each used only if its key is set)

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
        return jsonify({"files": []})
    files = []
    for name in ["ads_dataset.json", "evaluation_report.csv", "evaluation_summary.txt", "iteration_quality_chart.png"]:
        p = out / name
        if p.exists():
            files.append({"name": name, "size": p.stat().st_size})
    return jsonify({"files": files})


@app.route("/api/output/<path:name>")
def api_output_file(name):
    if name not in ("ads_dataset.json", "evaluation_report.csv", "evaluation_summary.txt", "iteration_quality_chart.png"):
        return "Forbidden", 403
    return send_from_directory(ROOT / "output", name, as_attachment=True)


@app.route("/api/run_history")
def api_run_history():
    """Return run history for ROI dashboard."""
    import json
    path = ROOT / "output" / "run_history.json"
    if not path.exists():
        return jsonify([])
    try:
        with open(path) as f:
            data = json.load(f)
        return jsonify(data if isinstance(data, list) else [])
    except Exception:
        return jsonify([])


@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nerdy Ad Engine — AI Ad Copy for Facebook & Instagram</title>
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
</head>
<body class="min-h-screen bg-surface-50 text-slate-800 font-sans antialiased">
  <!-- Header -->
  <header class="border-b border-slate-200/80 bg-white/90 backdrop-blur-sm sticky top-0 z-10">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-2xl font-bold tracking-tight text-slate-900">Nerdy</span>
        <span class="text-2xl font-semibold text-primary-600">Ad Engine</span>
      </div>
      <span class="text-sm text-slate-500 hidden sm:inline">Facebook &amp; Instagram</span>
      <a href="/dashboard" class="text-sm font-medium text-primary-600 hover:text-primary-700">Dashboard</a>
    </div>
  </header>

  <main class="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
    <!-- Hero -->
    <section class="text-center mb-10 sm:mb-12">
      <h1 class="text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight mb-3">Generate ad copy that performs</h1>
      <p class="text-lg text-slate-600 max-w-xl mx-auto">Create and score Facebook &amp; Instagram ads with AI. We generate copy, evaluate it on clarity, value, and brand voice, then iterate until it hits your quality bar.</p>
    </section>

    <!-- Generator card -->
    <section class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden mb-6">
      <div class="px-6 py-5 border-b border-slate-100">
        <h2 class="text-lg font-semibold text-slate-900">New run</h2>
        <p class="text-sm text-slate-500 mt-0.5">Configure your batch and start generation. API key in <code class="text-xs bg-slate-100 px-1.5 py-0.5 rounded">.env</code> is used if left blank.</p>
      </div>
      <form id="form" class="p-6 space-y-5">
        <div>
          <label for="api_key" class="block text-sm font-medium text-slate-700 mb-1.5">Gemini API key</label>
          <input type="password" id="api_key" name="api_key" placeholder="Optional if set in .env" autocomplete="off"
            class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
        </div>
        <div class="border-t border-slate-100 pt-4 mt-2">
          <p class="text-sm font-medium text-slate-700 mb-2">Or use OpenRouter (free models)</p>
          <p class="text-xs text-slate-500 mb-3">When Gemini quota is exceeded, use an <a href="https://openrouter.ai/keys" target="_blank" rel="noopener" class="text-primary-600 hover:underline">OpenRouter</a> key with free models. Key in <code class="text-xs bg-slate-100 px-1 rounded">.env</code> is used if left blank. If you get 401 Unauthorized, leave this blank to use the full key from .env.</p>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label for="openrouter_api_key" class="block text-sm font-medium text-slate-600 mb-1">OpenRouter API key</label>
              <input type="text" id="openrouter_api_key" name="openrouter_api_key" placeholder="Paste key or leave blank to use .env" autocomplete="off"
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm font-mono">
            </div>
            <div>
              <label for="openrouter_model" class="block text-sm font-medium text-slate-600 mb-1">Model</label>
              <input type="text" id="openrouter_model" name="openrouter_model" value="openrouter/free" placeholder="openrouter/free"
                class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
            </div>
          </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label for="num_ads" class="block text-sm font-medium text-slate-700 mb-1.5">Number of ads</label>
            <input type="number" id="num_ads" name="num_ads" value="5" min="1" max="100"
              class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
          </div>
          <div>
            <label for="max_iterations" class="block text-sm font-medium text-slate-700 mb-1.5">Max iterations per ad</label>
            <input type="number" id="max_iterations" name="max_iterations" value="6" min="1" max="10"
              class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
          </div>
          <div>
            <label for="seed" class="block text-sm font-medium text-slate-700 mb-1.5">Random seed</label>
            <input type="number" id="seed" name="seed" value="42"
              class="block w-full rounded-lg border-slate-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm">
          </div>
        </div>
        <div class="pt-1">
          <button type="submit" id="runBtn"
            class="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-6 py-3 bg-primary-600 text-white font-semibold rounded-lg shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed transition-colors">
            <svg id="runIcon" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            <span id="runLabel">Run generator</span>
          </button>
        </div>
      </form>
    </section>

    <!-- Progress (hidden by default) -->
    <section id="progressCard" class="hidden bg-white rounded-2xl shadow-sm border border-slate-200/80 p-6 mb-6">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-slate-700">Generating ads</h3>
        <span id="progressPct" class="text-sm font-medium text-primary-600">0%</span>
      </div>
      <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div id="progressFill" class="progress-fill h-full bg-primary-500 rounded-full" style="width:0%"></div>
      </div>
      <p id="progressText" class="text-sm text-slate-500 mt-2">—</p>
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

    <!-- Generated ads: full copy visible after run (ads are text, not PNGs) -->
    <section id="generatedAdsCard" class="hidden mb-6">
      <h3 class="text-lg font-semibold text-slate-900 mb-1">Your generated ads</h3>
      <p class="text-sm text-slate-500 mb-4">Ad copy (headline, primary text, CTA) for Facebook &amp; Instagram. These are text assets; use them in Meta Ads Manager or your creative tool. The only PNG download is the quality chart.</p>
      <div id="generatedAdsList" class="space-y-4"></div>
    </section>

    <!-- Output files (hidden by default) -->
    <section id="outputsCard" class="hidden bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100">
        <h3 class="text-lg font-semibold text-slate-900">Downloads</h3>
        <p class="text-sm text-slate-500 mt-0.5">Generated datasets and reports from the last run.</p>
      </div>
      <ul id="outputList" class="divide-y divide-slate-100"></ul>
    </section>
  </main>

  <footer class="border-t border-slate-200 mt-12 py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 text-center text-sm text-slate-500">
      Nerdy Ad Engine — autonomous generation and evaluation for Varsity Tutors / Nerdy.
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
    const resultCard = document.getElementById('resultCard');
    const resultBody = document.getElementById('resultBody');
    const resultError = document.getElementById('resultError');
    const outputsCard = document.getElementById('outputsCard');
    const outputList = document.getElementById('outputList');
    const liveAdsList = document.getElementById('liveAdsList');
    const generatedAdsCard = document.getElementById('generatedAdsCard');
    const generatedAdsList = document.getElementById('generatedAdsList');

    let pollTimer = null;

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
        const primary = esc((copy.primary_text || '').slice(0, 140));
        const score = ad.overall_score != null ? Number(ad.overall_score) : '—';
        const accepted = ad.accepted ? '<span class="inline-flex items-center rounded-full bg-primary-100 text-primary-800 text-xs font-medium px-2 py-0.5">Accepted</span>' : '<span class="inline-flex items-center rounded-full bg-slate-100 text-slate-600 text-xs font-medium px-2 py-0.5">Below threshold</span>';
        return '<div class="rounded-xl border border-slate-200 bg-slate-50/50 p-3 text-left shadow-sm">' +
          '<div class="flex items-start justify-between gap-2">' +
            '<span class="font-semibold text-slate-800 text-sm">' + headline + '</span>' +
            '<span class="text-sm font-medium text-slate-600 shrink-0">' + score + '</span>' +
          '</div>' +
          '<p class="text-xs text-slate-600 mt-1 line-clamp-2">' + primary + (primary.length >= 140 ? '…' : '') + '</p>' +
          '<div class="mt-2">' + accepted + '</div>' +
          '</div>';
      }).join('');
    }

    function renderGeneratedAds(completedAds) {
      if (!generatedAdsList) return;
      if (!completedAds || completedAds.length === 0) {
        generatedAdsList.innerHTML = '<p class="text-sm text-slate-400">No ads to show.</p>';
        return;
      }
      generatedAdsList.innerHTML = completedAds.map(function(ad, idx) {
        const copy = ad.ad_copy || {};
        const headline = esc(copy.headline || '—');
        const primary = esc(copy.primary_text || '');
        const description = esc(copy.description || '');
        const cta = esc(copy.cta || '');
        const score = ad.overall_score != null ? Number(ad.overall_score) : '—';
        const accepted = ad.accepted;
        const badge = accepted ? '<span class="inline-flex items-center rounded-full bg-primary-100 text-primary-800 text-xs font-medium px-2 py-0.5">Accepted</span>' : '<span class="inline-flex items-center rounded-full bg-slate-100 text-slate-600 text-xs font-medium px-2 py-0.5">Below threshold</span>';
        return '<div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm text-left">' +
          '<div class="flex items-center justify-between gap-2 flex-wrap">' +
            '<span class="text-xs font-medium text-slate-400">Ad ' + (idx + 1) + '</span>' +
            '<span class="text-sm font-semibold text-slate-700">Score: ' + score + '</span>' +
            badge +
          '</div>' +
          '<h4 class="font-semibold text-slate-900 mt-2 text-base">' + headline + '</h4>' +
          (primary ? '<p class="text-sm text-slate-700 mt-2 whitespace-pre-wrap">' + primary + '</p>' : '') +
          (description ? '<p class="text-sm text-slate-600 mt-1">' + description + '</p>' : '') +
          (cta ? '<p class="text-sm font-medium text-primary-600 mt-2">CTA: ' + cta + '</p>' : '') +
          '</div>';
      }).join('');
    }

    function showProgress(show) {
      progressCard.classList.toggle('hidden', !show);
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
      fetch('/api/status').then(r => r.json()).then(data => {
        const total = data.total || 1;
        const pct = Math.round((data.current / total) * 100);
        progressFill.style.width = pct + '%';
        progressPct.textContent = pct + '%';
        progressText.textContent = data.message || data.current + ' / ' + data.total;

        if (data.status === 'running' && data.completed_ads) {
          renderLiveAds(data.completed_ads);
        }

        if (data.status === 'done') {
          clearInterval(pollTimer);
          runBtn.disabled = false;
          runLabel.textContent = 'Run generator';
          runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>';
          showProgress(false);
          resultError.classList.add('hidden');
          resultBody.innerHTML = statCard('Ads generated', data.result.num_ads) +
            statCard('Accepted (≥7.0)', data.result.accepted) +
            statCard('Average score', data.result.avg_score) +
            (data.result.total_tokens != null ? statCard('Total tokens', data.result.total_tokens.toLocaleString()) : '') +
            (data.result.estimated_cost_usd != null ? statCard('Est. cost', '$' + data.result.estimated_cost_usd) : '') +
            (data.result.roi_accepted_per_1k_tokens != null ? statCard('ROI (accepted/1K tok)', data.result.roi_accepted_per_1k_tokens) : '') +
            statCard('Output', '<span class="text-sm font-mono text-slate-600 truncate block" title="' + data.result.output_dir + '">' + data.result.output_dir.replace(/.*[/\\\\]/, '') + '</span>');
          showResult(true);
          if (data.completed_ads && data.completed_ads.length > 0) {
            renderGeneratedAds(data.completed_ads);
            showGeneratedAds(true);
          } else {
            showGeneratedAds(false);
          }
          fetchOutputs();
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
        outputList.innerHTML = data.files.map(f => {
          const size = f.size ? (Math.round(f.size / 1024) + ' KB') : '';
          return '<li class="flex items-center justify-between gap-4 px-6 py-3 hover:bg-slate-50/80"><a href="/api/output/' + f.name + '" download class="font-medium text-primary-600 hover:text-primary-700 truncate">' + f.name + '</a><span class="text-sm text-slate-400 shrink-0">' + size + '</span></li>';
        }).join('');
        showOutputs(data.files.length > 0);
      });
    }

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      const api_key = (document.getElementById('api_key') && document.getElementById('api_key').value) ? document.getElementById('api_key').value.trim() : '';
      const openrouter_api_key = (document.getElementById('openrouter_api_key') && document.getElementById('openrouter_api_key').value) ? document.getElementById('openrouter_api_key').value.trim() : '';
      const openrouter_model = (document.getElementById('openrouter_model') && document.getElementById('openrouter_model').value) ? document.getElementById('openrouter_model').value.trim() : 'openrouter/free';
      const num_ads = parseInt(document.getElementById('num_ads').value, 10) || 5;
      const max_iterations = parseInt(document.getElementById('max_iterations').value, 10) || 6;
      const seed = parseInt(document.getElementById('seed').value, 10) || 42;
      runBtn.disabled = true;
      runLabel.textContent = 'Running…';
      runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>';
      showProgress(true);
      showResult(false);
      showGeneratedAds(false);
      fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: api_key || undefined, openrouter_api_key: openrouter_api_key || undefined, openrouter_model: openrouter_model || undefined, num_ads, max_iterations, seed })
      }).then(r => r.json()).then(data => {
        if (data.ok) pollTimer = setInterval(poll, 800);
        else { runBtn.disabled = false; runLabel.textContent = 'Run generator'; runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>'; showProgress(false); alert(data.error || 'Failed to start'); }
      }).catch(function() {
        runBtn.disabled = false;
        runLabel.textContent = 'Run generator';
        runIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>';
        showProgress(false);
        alert('Request failed');
      });
    });

    fetchOutputs();
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
  <title>ROI Dashboard — Nerdy Ad Engine</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    tailwind.config = { theme: { extend: { fontFamily: { sans: ['DM Sans', 'sans-serif'] }, colors: { primary: { 500: '#10b981', 600: '#059669' } } } } }
  </script>
</head>
<body class="min-h-screen bg-slate-50 text-slate-800 font-sans antialiased">
  <header class="border-b bg-white shadow-sm">
    <div class="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
      <a href="/" class="text-xl font-bold text-slate-900">Nerdy <span class="text-primary-600">Ad Engine</span></a>
      <a href="/" class="text-sm text-slate-600 hover:text-primary-600">← Generator</a>
    </div>
  </header>
  <main class="max-w-6xl mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold text-slate-900 mb-2">ROI Dashboard</h1>
    <p class="text-slate-600 mb-6">Was it worth the tokens? Track cost, accepted ads, and value per run.</p>

    <div id="summaryCards" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-8"></div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <h3 class="font-semibold text-slate-800 mb-3">Tokens per run</h3>
        <canvas id="chartTokens" height="200"></canvas>
      </div>
      <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <h3 class="font-semibold text-slate-800 mb-3">Est. cost (USD) per run</h3>
        <canvas id="chartCost" height="200"></canvas>
      </div>
    </div>
    <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm mb-8">
      <h3 class="font-semibold text-slate-800 mb-3">Accepted ads per run</h3>
      <canvas id="chartAccepted" height="200"></canvas>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
      <h3 class="font-semibold text-slate-800 px-4 py-3 border-b border-slate-100">Run history</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="bg-slate-50 text-left text-slate-600 font-medium">
            <th class="px-4 py-2">Time</th>
            <th class="px-4 py-2">Ads</th>
            <th class="px-4 py-2">Accepted</th>
            <th class="px-4 py-2">Score</th>
            <th class="px-4 py-2">Tokens</th>
            <th class="px-4 py-2">Cost</th>
            <th class="px-4 py-2">ROI (accepted/1K tok)</th>
            <th class="px-4 py-2">Score/$</th>
          </tr></thead>
          <tbody id="runHistoryBody"></tbody>
        </table>
      </div>
      <p id="noRuns" class="hidden px-4 py-6 text-slate-500 text-center">No runs yet. Generate ads to see ROI here.</p>
    </div>
  </main>

  <script>
    fetch('/api/run_history').then(r => r.json()).then(function(runs) {
      const cards = document.getElementById('summaryCards');
      const tbody = document.getElementById('runHistoryBody');
      const noRuns = document.getElementById('noRuns');

      if (!runs || runs.length === 0) {
        noRuns.classList.remove('hidden');
        cards.innerHTML = '<p class="col-span-full text-slate-500">Run the generator to populate ROI metrics.</p>';
        return;
      }

      const totalTokens = runs.reduce(function(s, r) { return s + (r.total_tokens || 0); }, 0);
      const totalCost = runs.reduce(function(s, r) { return s + (r.estimated_cost_usd || 0); }, 0);
      const totalAccepted = runs.reduce(function(s, r) { return s + (r.accepted || 0); }, 0);
      const avgRoi = runs.length ? runs.reduce(function(s, r) { return s + (r.roi_accepted_per_1k_tokens || 0); }, 0) / runs.length : 0;
      const avgScorePerDollar = runs.length ? runs.reduce(function(s, r) { return s + (r.roi_score_per_dollar || 0); }, 0) / runs.length : 0;

      cards.innerHTML =
        '<div class="bg-white rounded-xl border p-4 shadow-sm"><p class="text-xs text-slate-500 uppercase">Runs</p><p class="text-2xl font-bold text-slate-900">' + runs.length + '</p></div>' +
        '<div class="bg-white rounded-xl border p-4 shadow-sm"><p class="text-xs text-slate-500 uppercase">Total tokens</p><p class="text-2xl font-bold text-slate-900">' + totalTokens.toLocaleString() + '</p></div>' +
        '<div class="bg-white rounded-xl border p-4 shadow-sm"><p class="text-xs text-slate-500 uppercase">Est. cost</p><p class="text-2xl font-bold text-slate-900">$' + totalCost.toFixed(4) + '</p></div>' +
        '<div class="bg-white rounded-xl border p-4 shadow-sm"><p class="text-xs text-slate-500 uppercase">Accepted ads</p><p class="text-2xl font-bold text-primary-600">' + totalAccepted + '</p></div>' +
        '<div class="bg-white rounded-xl border p-4 shadow-sm"><p class="text-xs text-slate-500 uppercase">ROI (accepted/1K tok)</p><p class="text-2xl font-bold text-slate-900">' + avgRoi.toFixed(3) + '</p></div>' +
        '<div class="bg-white rounded-xl border p-4 shadow-sm"><p class="text-xs text-slate-500 uppercase">Score / $</p><p class="text-2xl font-bold text-slate-900">' + avgScorePerDollar.toFixed(1) + '</p></div>';

      tbody.innerHTML = runs.slice().reverse().map(function(r) {
        const t = (r.timestamp || '').replace('T', ' ').slice(0, 19);
        return '<tr class="border-t border-slate-100 hover:bg-slate-50">' +
          '<td class="px-4 py-2 font-mono text-xs">' + t + '</td>' +
          '<td class="px-4 py-2">' + (r.num_ads || 0) + '</td>' +
          '<td class="px-4 py-2">' + (r.accepted || 0) + '</td>' +
          '<td class="px-4 py-2">' + (r.avg_score != null ? r.avg_score : '—') + '</td>' +
          '<td class="px-4 py-2">' + (r.total_tokens != null ? r.total_tokens.toLocaleString() : '—') + '</td>' +
          '<td class="px-4 py-2">$' + (r.estimated_cost_usd != null ? r.estimated_cost_usd : 0) + '</td>' +
          '<td class="px-4 py-2">' + (r.roi_accepted_per_1k_tokens != null ? r.roi_accepted_per_1k_tokens.toFixed(3) : '—') + '</td>' +
          '<td class="px-4 py-2">' + (r.roi_score_per_dollar != null ? r.roi_score_per_dollar : '—') + '</td>' +
          '</tr>';
      }).join('');

      const labels = runs.slice().reverse().map(function(r) { return (r.timestamp || '').slice(0, 16); });
      new Chart(document.getElementById('chartTokens'), {
        type: 'line',
        data: { labels: labels, datasets: [{ label: 'Tokens', data: runs.slice().reverse().map(function(r) { return r.total_tokens || 0; }), borderColor: '#10b981', fill: false }] },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
      });
      new Chart(document.getElementById('chartCost'), {
        type: 'line',
        data: { labels: labels, datasets: [{ label: 'Cost (USD)', data: runs.slice().reverse().map(function(r) { return r.estimated_cost_usd || 0; }), borderColor: '#059669', fill: false }] },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
      });
      new Chart(document.getElementById('chartAccepted'), {
        type: 'bar',
        data: { labels: labels, datasets: [{ label: 'Accepted', data: runs.slice().reverse().map(function(r) { return r.accepted || 0; }), backgroundColor: '#10b981' }] },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
      });
    });
  </script>
</body>
</html>
"""


def main():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
