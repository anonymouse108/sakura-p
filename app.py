from flask import Flask, send_file, jsonify
import threading
import time
import os
from datetime import datetime

app = Flask(__name__)

proxy_count = 0
last_update = "Never"

# Include your existing fetch_urban_vpn_proxies() here

def updater():
    global proxy_count, last_update

    while True:
        try:
            proxies = fetch_urban_vpn_proxies()

            with open("proxies.txt", "w") as f:
                for p in proxies:
                    f.write(
                        f"{p['ip']}:{p['port']}:{p['user']}:{p['pass']}\n"
                    )

            proxy_count = len(proxies)
            last_update = datetime.utcnow().isoformat()

            print(f"Updated {proxy_count} proxies")

        except Exception as e:
            print(e)

        time.sleep(120)


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "proxies": proxy_count,
        "last_update": last_update
    })


@app.route("/proxies.txt")
def proxies():
    return send_file(
        "proxies.txt",
        mimetype="text/plain"
    )


threading.Thread(target=updater, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
