"""Web interface for Nerdy Autonomous Ad Engine."""

import os
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_from_directory

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
}


def _progress_callback(current, total, message):
    _run_state["current"] = current
    _run_state["total"] = total
    _run_state["message"] = message


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

    # Optional: set API key from request (not persisted; used only for this process)
    api_key = (data.get("api_key") or "").strip()
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key

    _run_state.update(
        status="running",
        current=0,
        total=num_ads,
        message="Starting...",
        result=None,
        error=None,
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


INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nerdy Ad Engine</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 640px; margin: 0 auto; padding: 1.5rem; background: #f8f9fa; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    .sub { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
    .card { background: #fff; border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    label { display: block; font-weight: 500; margin-bottom: 0.25rem; font-size: 0.9rem; }
    input[type=number] { width: 100%; padding: 0.5rem; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 0.75rem; }
    input[type=password] { width: 100%; padding: 0.5rem; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 0.75rem; }
    button { background: #0d6efd; color: #fff; border: none; padding: 0.6rem 1.2rem; border-radius: 6px; font-weight: 500; cursor: pointer; }
    button:hover { background: #0b5ed7; }
    button:disabled { background: #adb5bd; cursor: not-allowed; }
    .progress-wrap { margin: 1rem 0; }
    .progress-bar { height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden; }
    .progress-fill { height: 100%; background: #0d6efd; transition: width 0.2s; }
    .progress-text { font-size: 0.85rem; color: #666; margin-top: 0.25rem; }
    .result { font-size: 0.9rem; }
    .result dt { font-weight: 600; margin-top: 0.5rem; }
    .result dd { margin: 0; color: #333; }
    .files { list-style: none; padding: 0; margin: 0; }
    .files li { padding: 0.35rem 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
    .files a { color: #0d6efd; text-decoration: none; }
    .files a:hover { text-decoration: underline; }
    .error { color: #dc3545; font-size: 0.9rem; }
    .hidden { display: none; }
    .muted { font-weight: normal; color: #6c757d; }
  </style>
</head>
<body>
  <h1>Nerdy Autonomous Ad Engine</h1>
  <p class="sub">Generate and evaluate Facebook &amp; Instagram ad copy. Set GEMINI_API_KEY in the environment before running.</p>

  <div class="card">
    <form id="form">
      <label for="api_key">Gemini API key <span class="muted">(optional if set in .env)</span></label>
      <input type="password" id="api_key" name="api_key" placeholder="Paste your key here" autocomplete="off">
      <label for="num_ads">Number of ads</label>
      <input type="number" id="num_ads" name="num_ads" value="5" min="1" max="100">
      <label for="max_iterations">Max iterations per ad</label>
      <input type="number" id="max_iterations" name="max_iterations" value="6" min="1" max="10">
      <label for="seed">Random seed</label>
      <input type="number" id="seed" name="seed" value="42">
      <button type="submit" id="runBtn">Run</button>
    </form>
  </div>

  <div class="card hidden" id="progressCard">
    <div class="progress-wrap">
      <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
      <div class="progress-text" id="progressText">—</div>
    </div>
  </div>

  <div class="card hidden" id="resultCard">
    <h3>Result</h3>
    <dl class="result" id="resultBody"></dl>
    <p class="hidden error" id="resultError"></p>
  </div>

  <div class="card hidden" id="outputsCard">
    <h3>Output files</h3>
    <ul class="files" id="outputList"></ul>
  </div>

  <script>
    const form = document.getElementById('form');
    const runBtn = document.getElementById('runBtn');
    const progressCard = document.getElementById('progressCard');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultCard = document.getElementById('resultCard');
    const resultBody = document.getElementById('resultBody');
    const resultError = document.getElementById('resultError');
    const outputsCard = document.getElementById('outputsCard');
    const outputList = document.getElementById('outputList');

    let pollTimer = null;

    function showProgress(show) {
      progressCard.classList.toggle('hidden', !show);
    }
    function showResult(show) {
      resultCard.classList.toggle('hidden', !show);
    }
    function showOutputs(show) {
      outputsCard.classList.toggle('hidden', !show);
    }

    function poll() {
      fetch('/api/status').then(r => r.json()).then(data => {
        const pct = data.total ? Math.round((data.current / data.total) * 100) : 0;
        progressFill.style.width = pct + '%';
        progressText.textContent = data.message || data.current + ' / ' + data.total;

        if (data.status === 'done') {
          clearInterval(pollTimer);
          runBtn.disabled = false;
          showProgress(false);
          resultError.classList.add('hidden');
          resultBody.innerHTML = '<dt>Ads generated</dt><dd>' + data.result.num_ads + '</dd>' +
            '<dt>Accepted (≥7.0)</dt><dd>' + data.result.accepted + '</dd>' +
            '<dt>Average score</dt><dd>' + data.result.avg_score + '</dd>' +
            '<dt>Output</dt><dd>' + data.result.output_dir + '</dd>';
          showResult(true);
          fetchOutputs();
        } else if (data.status === 'error') {
          clearInterval(pollTimer);
          runBtn.disabled = false;
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
        outputList.innerHTML = data.files.map(f => 
          '<li><a href="/api/output/' + f.name + '" download>' + f.name + '</a> ' + (f.size ? (Math.round(f.size/1024) + ' KB') : '') + '</li>'
        ).join('');
        showOutputs(data.files.length > 0);
      });
    }

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      const api_key = (document.getElementById('api_key') && document.getElementById('api_key').value) ? document.getElementById('api_key').value.trim() : '';
      const num_ads = parseInt(document.getElementById('num_ads').value, 10) || 5;
      const max_iterations = parseInt(document.getElementById('max_iterations').value, 10) || 6;
      const seed = parseInt(document.getElementById('seed').value, 10) || 42;
      runBtn.disabled = true;
      showProgress(true);
      showResult(false);
      fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: api_key || undefined, num_ads, max_iterations, seed })
      }).then(r => r.json()).then(data => {
        if (data.ok) pollTimer = setInterval(poll, 800);
        else { runBtn.disabled = false; showProgress(false); alert(data.error || 'Failed to start'); }
      }).catch(() => { runBtn.disabled = false; showProgress(false); alert('Request failed'); });
    });

    // On load: show existing output files if any (e.g. from a previous run)
    fetchOutputs();
  </script>
</body>
</html>
"""


def main():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
