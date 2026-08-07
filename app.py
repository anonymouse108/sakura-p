from flask import Flask, send_file, jsonify
import threading
import time
import os
from datetime import datetime
import urllib3

from fetcher import fetch_urban_vpn_proxies

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "proxies.txt")

REFRESH_INTERVAL = 120

last_update = "Never"
proxy_count = 0
is_fetching = False

fetch_lock = threading.Lock()


def log(message):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] {message}", flush=True)


def save_proxies(proxies):
    global proxy_count, last_update

    temp_file = PROXY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        for p in proxies:
            f.write(
                f"{p['ip']}:{p['port']}:{p['user']}:{p['pass']}\n"
            )

    os.replace(temp_file, PROXY_FILE)

    proxy_count = len(proxies)
    last_update = datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def fetch_once():
    global is_fetching

    if not fetch_lock.acquire(blocking=False):
        log("[!] Fetch already running.")
        return False

    is_fetching = True
    start = time.time()

    try:
        log("=" * 60)
        log("[*] STARTING PROXY FETCH")
        log("[*] Fetching fresh proxies from Urban VPN...")

        proxies = fetch_urban_vpn_proxies()

        elapsed = time.time() - start

        if not proxies:
            log(
                f"[-] Fetch finished: 0 proxies "
                f"({elapsed:.2f}s)"
            )
            return False

        save_proxies(proxies)

        log(
            f"[+] SUCCESS: {len(proxies)} proxies fetched "
            f"in {elapsed:.2f}s"
        )
        log(f"[+] Saved to: {PROXY_FILE}")
        log(f"[+] Next automatic refresh in {REFRESH_INTERVAL}s")

        return True

    except Exception as e:
        log(
            f"[!] FETCH ERROR: "
            f"{type(e).__name__}: {e}"
        )
        return False

    finally:
        is_fetching = False
        fetch_lock.release()


def update_proxies():
    """
    Fetch immediately on startup, then every 2 minutes.
    """

    log("[+] AUTO-FETCHER STARTED")
    log("[+] Performing INITIAL FETCH NOW")

    # Immediate startup fetch
    fetch_once()

    # Continue refreshing every 2 minutes
    while True:

        log(
            f"[*] Sleeping {REFRESH_INTERVAL} seconds..."
        )

        time.sleep(REFRESH_INTERVAL)

        log("[*] 2-minute interval reached.")
        fetch_once()


def start_background_fetcher():
    """
    Start the fetcher immediately when app.py is imported
    by Gunicorn.
    """

    thread = threading.Thread(
        target=update_proxies,
        daemon=True,
        name="proxy-auto-fetcher"
    )

    thread.start()

    log("[+] Background auto-fetcher thread started.")


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "proxy_count": proxy_count,
        "last_update": last_update,
        "refresh_interval": "120 seconds",
        "fetching": is_fetching,
        "proxy_file_exists": os.path.exists(PROXY_FILE),
        "download": "/proxies.txt",
        "manual_refresh": "/refresh",
        "health": "/health"
    })


@app.route("/proxies.txt")
def proxies():

    if not os.path.exists(PROXY_FILE):
        return (
            "Proxy list is being generated...",
            503,
            {"Cache-Control": "no-cache"}
        )

    return send_file(
        PROXY_FILE,
        mimetype="text/plain",
        as_attachment=False,
        download_name="proxies.txt",
        max_age=0
    )


@app.route("/refresh")
def refresh():

    if is_fetching:
        return jsonify({
            "status": "already_fetching",
            "message": "A proxy fetch is already running."
        }), 409

    threading.Thread(
        target=fetch_once,
        daemon=True,
        name="manual-fetch"
    ).start()

    return jsonify({
        "status": "started",
        "message": "Manual refresh started."
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "proxy_file_exists": os.path.exists(PROXY_FILE),
        "proxy_count": proxy_count,
        "fetching": is_fetching,
        "last_update": last_update
    })


# ============================================================
# IMPORTANT:
# This runs when Gunicorn imports app:app.
#
# It immediately starts:
#
#     fetch_once()
#
# and then repeats every 120 seconds.
# ============================================================

start_background_fetcher()


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    log(f"[*] Starting Flask on port {port}")

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )
