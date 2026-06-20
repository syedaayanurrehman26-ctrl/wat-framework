#!/usr/bin/env python3
"""
ThreadIntel — Single-command runner.

Starts worker.py and deliver.py in parallel background threads so you
only need one terminal window. Both keep polling until you Ctrl-C.

Also serves a health check endpoint on PORT (default 8080) so cloud
platforms (DigitalOcean, Railway, Render) know the process is alive.

Usage:
    python threadintel/run.py
"""

import os
import sys
import time
import threading
import traceback
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
)
log = logging.getLogger("threadintel.run")

_started_at = datetime.now(timezone.utc).isoformat()
_stats = {"worker_batches": 0, "reports_ok": 0, "reports_fail": 0, "delivered": 0}


# ── Worker loop ───────────────────────────────────────────────────────────────

def _run_worker():
    import worker
    log.info("[worker] starting")
    while True:
        try:
            ok, fail = worker.process_batch()
            _stats["worker_batches"] += 1
            _stats["reports_ok"]    += ok
            _stats["reports_fail"]  += fail
            if ok or fail:
                log.info("[worker] batch: %d ok, %d failed", ok, fail)
        except Exception:
            traceback.print_exc()
        time.sleep(10)


def _run_deliver():
    import deliver
    log.info("[deliver] starting")
    while True:
        try:
            n = deliver.process_batch()
            if n:
                _stats["delivered"] += n
                log.info("[deliver] delivered %d report(s)", n)
        except Exception:
            traceback.print_exc()
        time.sleep(15)


# ── Health check server ───────────────────────────────────────────────────────

def _run_health_server():
    """Tiny Flask server for /health — lets hosting platforms confirm we're alive."""
    try:
        from flask import Flask, jsonify
        app = Flask("threadintel-health")
        app.logger.disabled = True
        log_wz = logging.getLogger("werkzeug")
        log_wz.setLevel(logging.WARNING)

        @app.route("/health")
        def health():
            return jsonify({
                "status": "ok",
                "started_at": _started_at,
                "uptime_s": int((datetime.now(timezone.utc) -
                                 datetime.fromisoformat(_started_at)).total_seconds()),
                **_stats,
            })

        @app.route("/")
        def root():
            return "ThreadIntel worker running", 200

        port = int(os.getenv("PORT", "8080"))
        log.info("[health] listening on :%d", port)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        log.warning("[health] server failed to start: %s", e)


if __name__ == "__main__":
    # Validate env vars before starting threads — catch misconfigured deploys immediately
    sys.path.insert(0, str(Path(__file__).parent))
    import worker as _w
    _w._startup_check()

    log.info("ThreadIntel starting")
    log.info("  worker  → polls for queued reports every 10s")
    log.info("  deliver → polls for done reports every 15s")
    log.info("  health  → GET /health on PORT=%s", os.getenv("PORT", "8080"))

    threads = [
        threading.Thread(target=_run_worker,        daemon=True, name="worker"),
        threading.Thread(target=_run_deliver,        daemon=True, name="deliver"),
        threading.Thread(target=_run_health_server,  daemon=True, name="health"),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("ThreadIntel stopped.")
