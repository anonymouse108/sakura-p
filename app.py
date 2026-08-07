from flask import Flask, send_file, jsonify
import threading
import time
import os
from datetime import datetime
import urllib3

from fetcher import fetch_urban_vpn_proxies

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "proxies.txt")

REFRESH_INTERVAL = 120  # 2 minutes

# --------------------------------------------------
# STATE
# --------------------------------------------------

last_update = "Never"
proxy_count = 0
is_fetching = False

# Prevent multiple fetches from running simultaneously
fetch_lock = threading.Lock()

# --------------------------------------------------
# PROXY FILE
# --------------------------------------------------

def save_proxies(proxies):
    """
    Save proxies atomically so /proxies.txt never
    serves a partially-written file.
    """

    global proxy_count, last_update

    temp_file = PROXY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        for proxy in proxies:
            f.write(
                f"{proxy['ip']}:{proxy['port']}:{proxy['user']}:{proxy['pass']}\n"
            )

    # Replace old file only after the new file is
    # completely written.
    os.replace(temp_file, PROXY_FILE)

    proxy_count = len(proxies)
    last_update = datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


# --------------------------------------------------
# FETCH
# --------------------------------------------------

def fetch_once():
    """
    Perform one complete proxy fetch.
    """

    global is_fetching

    # Don't allow two fetches at the same time
    if not fetch_lock.acquire(blocking=False):
        print("[!] Proxy fetch already running.")
        return False

    is_fetching = True
    start_time = time.time()

    try:
        print("[*] Fetching fresh proxies...")

        proxies = fetch_urban_vpn_proxies()

        if not proxies:
            print("[-] No proxies fetched.")
            return False

        save_proxies(proxies)

        elapsed = time.time() - start_time

        print(
            f"[+] Updated {len(proxies)} proxies "
            f"in {elapsed:.2f}s"
        )

        return True

    except Exception as e:
        print(f"[!] Proxy update failed: {e}")
        return False

    finally:
        is_fetching = False
        fetch_lock.release()


# --------------------------------------------------
# AUTOMATIC FETCHER
# --------------------------------------------------

def update_proxies():
    """
    Automatically fetch proxies immediately on startup,
    then refresh every 120 seconds.
    """

    print("[*] Automatic proxy updater started.")

    while True:

        try:
            fetch_once()

        except Exception as e:
            # Extra protection so the updater thread
            # never dies permanently.
            print(f"[!] Updater thread error: {e}")

        print(
            f"[*] Next proxy refresh in "
            f"{REFRESH_INTERVAL} seconds."
        )

        time.sleep(REFRESH_INTERVAL)


# --------------------------------------------------
# API ROUTES
# --------------------------------------------------

@app.route("/")
def home():

    return jsonify({
        "status": "online",
        "proxy_count": proxy_count,
        "last_update": last_update,
        "refresh_interval": f"{REFRESH_INTERVAL} seconds",
        "fetching": is_fetching,
        "download": "/proxies.txt"
    })


@app.route("/proxies.txt")
def proxies():

    if not os.path.exists(PROXY_FILE):

        return (
            "Proxy list is being generated...",
            503
        )

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
            "message": "A proxy refresh is already running.",
            "fetching": True
        }), 409

    threading.Thread(
        target=fetch_once,
        daemon=True
    ).start()

    return jsonify({
        "message": "Manual refresh started",
        "fetching": True
    })


# --------------------------------------------------
# START BACKGROUND FETCHER
# --------------------------------------------------
#
# IMPORTANT:
#
# This is intentionally OUTSIDE:
#
#     if __name__ == "__main__":
#
# Railway uses Gunicorn:
#
#     gunicorn app:app
#
# Therefore __name__ is NOT "__main__".
#
# Putting the updater here ensures it starts when
# Gunicorn imports this module.
#
# --------------------------------------------------

_updater_started = False
_updater_start_lock = threading.Lock()


def start_updater():

    global _updater_started

    with _updater_start_lock:

        if _updater_started:
            return

        _updater_started = True

        updater_thread = threading.Thread(
            target=update_proxies,
            daemon=True,
            name="proxy-updater"
        )

        updater_thread.start()

        print("[+] Proxy updater thread started.")


start_updater()


# --------------------------------------------------
# LOCAL DEVELOPMENT
# --------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 8080)
    )

    print(
        f"[*] Starting Flask server "
        f"on 0.0.0.0:{port}"
    )

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )
