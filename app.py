from flask import Flask, send_file, jsonify
import threading
import time
import os
from datetime import datetime
import urllib3
from fetcher import fetch_urban_vpn_proxies

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

PROXY_FILE = "proxies.txt"

last_update = "Never"
proxy_count = 0
is_fetching = False


def update_proxies():
    global last_update, proxy_count, is_fetching

    while True:
        is_fetching = True
        start = time.time()

        try:
            console.print("[cyan]Fetching fresh proxies...[/cyan]")

            proxies = fetch_urban_vpn_proxies()

            if proxies:
                with open(PROXY_FILE, "w", encoding="utf-8") as f:
                    for p in proxies:
                        f.write(
                            f"{p['ip']}:{p['port']}:{p['user']}:{p['pass']}\n"
                        )

                proxy_count = len(proxies)
                last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

                console.print(
                    f"[green]✓ Updated {proxy_count} proxies in {time.time()-start:.2f}s[/green]"
                )
            else:
                console.print("[red]No proxies fetched.[/red]")

        except Exception as e:
            console.print(f"[red]Update failed: {e}[/red]")

        is_fetching = False

        # Wait exactly 2 minutes before next refresh
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
    threading.Thread(target=lambda: fetch_once(), daemon=True).start()
    return jsonify({"message": "Manual refresh started"})


def fetch_once():
    global proxy_count, last_update

    try:
        proxies = fetch_urban_vpn_proxies()

        if proxies:
            with open(PROXY_FILE, "w", encoding="utf-8") as f:
                for p in proxies:
                    f.write(
                        f"{p['ip']}:{p['port']}:{p['user']}:{p['pass']}\n"
                    )

            proxy_count = len(proxies)
            last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    except Exception as e:
        console.print(e)


if __name__ == "__main__":
    # Initial fetch immediately
    threading.Thread(target=update_proxies, daemon=True).start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        threaded=True
    )
