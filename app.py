from flask import Flask, send_file, jsonify
import threading
import time
import os
from datetime import datetime
import urllib3

from fetcher import fetch_urban_vpn_proxies

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "proxies.txt")

last_update = "Never"
proxy_count = 0
is_fetching = False

# Prevent manual refresh and automatic refresh from running simultaneously
fetch_lock = threading.Lock()


def save_proxies(proxies):
    """Save proxy list safely to proxies.txt."""
    global proxy_count, last_update

    temp_file = PROXY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        for p in proxies:
            f.write(
                f"{p['ip']}:{p['port']}:{p['user']}:{p['pass']}\n"
            )

    # Atomic replacement
    os.replace(temp_file, PROXY_FILE)

    proxy_count = len(proxies)
    last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch_once():
    """Perform one proxy fetch."""
    global is_fetching

    if not fetch_lock.acquire(blocking=False):
        print("[!] A proxy fetch is already running.")
        return False

    is_fetching = True
    start = time.time()

    try:
        print("[*] Fetching fresh proxies...")

        proxies = fetch_urban_vpn_proxies()

        if proxies:
            save_proxies(proxies)

            elapsed = time.time() - start

            print(
                f"[+] Updated {len(proxies)} proxies "
                f"in {elapsed:.2f}s"
            )

            return True

        print("[-] No proxies fetched.")
        return False

    except Exception as e:
        print(f"[!] Update failed: {e}")
        return False

    finally:
        is_fetching = False
        fetch_lock.release()


def update_proxies():
    """Continuously refresh proxies every 2 minutes."""

    while True:
        fetch_once()

        # Wait exactly 120 seconds before next refresh
        time.sleep(120)


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "proxy_count": proxy_count,
        "last_update": last_update,
        "refresh_interval": "120 seconds",
        "fetching": is_fetching,
        "download": "/proxies.txt"
    })


@app.route("/proxies.txt")
def proxies():
    if not os.path.exists(PROXY_FILE):
        return "Proxy list is being generated...", 503

    return send_file(
        PROXY_FILE,
        mimetype="text/plain",
        as_attachment=False,
        download_name="proxies.txt"
    )


@app.route("/refresh")
def refresh():
    if is_fetching:
        return jsonify({
            "message": "A proxy refresh is already running."
        }), 409

    threading.Thread(
        target=fetch_once,
        daemon=True
    ).start()

    return jsonify({
        "message": "Manual refresh started"
    })


if __name__ == "__main__":
    # Initial fetch immediately
    threading.Thread(
        target=update_proxies,
        daemon=True
    ).start()

    port = int(os.environ.get("PORT", 8080))

    print(f"[*] Starting Flask server on port {port}")

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )
