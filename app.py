from flask import Flask, send_file, jsonify
import threading
import time
import os
from datetime import datetime
import urllib3

from fetcher import fetch_urban_vpn_proxies


# ============================================================
# CONFIG
# ============================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_FILE = os.path.join(BASE_DIR, "proxies.txt")

REFRESH_INTERVAL = 120  # 2 minutes


# ============================================================
# GLOBAL STATE
# ============================================================

last_update = "Never"
proxy_count = 0
is_fetching = False

# Prevent two fetch operations from running simultaneously
fetch_lock = threading.Lock()

# Prevent the updater from accidentally being started twice
updater_start_lock = threading.Lock()
updater_started = False


# ============================================================
# LOGGING
# ============================================================

def log(message):
    """Print immediately so Railway captures the log."""
    print(
        f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}] "
        f"{message}",
        flush=True
    )


# ============================================================
# SAVE PROXIES
# ============================================================

def save_proxies(proxies):
    """
    Save the proxy list atomically.

    The new file is written completely first and then replaces
    the existing proxies.txt. This prevents clients from
    downloading a partially-written file.
    """

    global proxy_count, last_update

    temp_file = PROXY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        for proxy in proxies:
            try:
                ip = proxy["ip"]
                port = proxy["port"]
                user = proxy["user"]
                password = proxy["pass"]

                f.write(
                    f"{ip}:{port}:{user}:{password}\n"
                )

            except KeyError as e:
                log(f"[!] Invalid proxy entry, missing key: {e}")

    # Atomically replace the old file
    os.replace(temp_file, PROXY_FILE)

    proxy_count = len(proxies)

    last_update = datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


# ============================================================
# ONE PROXY FETCH
# ============================================================

def fetch_once():
    """
    Perform one proxy fetch.

    Returns:
        True  = successful fetch
        False = failed/no proxies
    """

    global is_fetching

    # Don't allow another fetch while one is running
    if not fetch_lock.acquire(blocking=False):
        log("[!] Proxy fetch already running. Skipping.")
        return False

    is_fetching = True

    start_time = time.time()

    try:
        log("=" * 60)
        log("[*] Starting proxy fetch...")
        log("[*] Calling Urban VPN fetcher...")

        proxies = fetch_urban_vpn_proxies()

        elapsed = time.time() - start_time

        if not proxies:
            log(
                f"[-] Fetch completed but returned 0 proxies "
                f"after {elapsed:.2f}s"
            )

            return False

        save_proxies(proxies)

        log(
            f"[+] Successfully fetched {len(proxies)} proxies "
            f"in {elapsed:.2f}s"
        )

        log(f"[+] Proxy file: {PROXY_FILE}")
        log(f"[+] Proxy count: {proxy_count}")
        log(f"[+] Last update: {last_update}")

        return True

    except Exception as e:

        elapsed = time.time() - start_time

        log(
            f"[!] Proxy fetch failed after {elapsed:.2f}s: "
            f"{type(e).__name__}: {e}"
        )

        return False

    finally:

        is_fetching = False

        try:
            fetch_lock.release()
        except RuntimeError:
            pass


# ============================================================
# AUTOMATIC PROXY UPDATER
# ============================================================

def update_proxies():
    """
    Run the initial fetch immediately and then refresh
    every 120 seconds.
    """

    log("[+] Automatic proxy updater started.")
    log(
        f"[*] Refresh interval: "
        f"{REFRESH_INTERVAL} seconds"
    )

    while True:

        try:
            fetch_once()

        except Exception as e:
            # Make absolutely sure the background thread
            # doesn't permanently die.
            log(
                f"[!] Unexpected updater error: "
                f"{type(e).__name__}: {e}"
            )

        log(
            f"[*] Waiting {REFRESH_INTERVAL} seconds "
            f"until next refresh..."
        )

        time.sleep(REFRESH_INTERVAL)


# ============================================================
# START UPDATER
# ============================================================

def start_updater():
    """
    Start the background updater exactly once.

    IMPORTANT:
    This is called when app.py is imported by Gunicorn.
    """

    global updater_started

    with updater_start_lock:

        if updater_started:
            log("[*] Proxy updater already started.")
            return

        updater_started = True

        thread = threading.Thread(
            target=update_proxies,
            daemon=True,
            name="proxy-updater"
        )

        thread.start()

        log("[+] Proxy updater thread launched.")


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "status": "online",
        "proxy_count": proxy_count,
        "last_update": last_update,
        "refresh_interval": f"{REFRESH_INTERVAL} seconds",
        "fetching": is_fetching,
        "proxy_file_exists": os.path.exists(PROXY_FILE),
        "download": "/proxies.txt",
        "manual_refresh": "/refresh"
    })


# ============================================================
# PROXY FILE
# ============================================================

@app.route("/proxies.txt")
def proxies():

    if not os.path.exists(PROXY_FILE):

        return (
            "Proxy list is being generated...",
            503,
            {
                "Cache-Control": "no-cache"
            }
        )

    return send_file(
        PROXY_FILE,
        mimetype="text/plain",
        as_attachment=False,
        download_name="proxies.txt",
        max_age=0
    )


# ============================================================
# MANUAL REFRESH
# ============================================================

@app.route("/refresh")
def refresh():

    if is_fetching:

        return jsonify({
            "status": "already_fetching",
            "message": "A proxy refresh is already running.",
            "fetching": True
        }), 409

    log("[*] Manual refresh requested.")

    thread = threading.Thread(
        target=fetch_once,
        daemon=True,
        name="manual-proxy-refresh"
    )

    thread.start()

    return jsonify({
        "status": "started",
        "message": "Manual proxy refresh started.",
        "fetching": True
    })


# ============================================================
# HEALTH CHECK
# ============================================================

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
# START BACKGROUND THREAD
# ============================================================
#
# DO NOT put this inside:
#
#     if __name__ == "__main__":
#
# Railway runs:
#
#     gunicorn app:app
#
# which imports this file rather than executing it as
# "__main__".
#
# ============================================================

start_updater()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 8080)
    )

    log(
        f"[*] Starting Flask development server "
        f"on 0.0.0.0:{port}"
    )

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )
