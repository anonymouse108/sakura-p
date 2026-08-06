#!/usr/bin/env python3
"""
SUKUNA PROXY FETCHER v1.1
High-performance proxy fetcher from Urban VPN with rich UI
"""

import sys
import os
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Callable

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich import box
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    import httpx
except ImportError:
    print("[!] Installing required packages...")
    os.system(f"{sys.executable} -m pip install rich httpx -q")
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich import box
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    import httpx

console = Console()

# Configuration
MAX_WORKERS = 50  # High threads for parallel fetching
TIMEOUT = 30

# Headers
HEADERS_VPN = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "chrome-extension://eppiocemhmnlbhjplcgkofciegomcon",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
}

# Banner
BANNER = f"""
[bold red]
   ▄▄▄▄▄▄▄ ▄▄   ▄▄ ▄▄▄▄▄▄▄ ▄▄   ▄▄ ▄▄    ▄ ▄▄▄▄▄▄▄ 
  █       █  █ █  █       █  █▄█  █  █  █ █       █
  █  ▄▄▄▄▄█  █ █  █   ▄   █       █   █▄█ █   ▄   █
  █ █▄▄▄▄▄█  █▄█  █  █▄█  █       █       █  █▄█  █
  █▄▄▄▄▄  █       █       █  ▄   ██  ▄    █       █
   ▄▄▄▄▄█ █       █   ▄   █ █▄█   █ █ █   █   ▄   █
  █▄▄▄▄▄▄▄█▄▄▄▄▄▄▄█▄▄█ █▄▄█▄▄▄▄▄▄▄█▄█  █▄▄█▄▄█ █▄▄█
[/bold red]
[bold magenta]╔══════════════════════════════════════════════════════╗
║         SUKUNA PROXY FETCHER v1.1                       ║
║     High-Performance Urban VPN Proxy Collector          ║
║     Max Workers: 50 │ Auto Retry │ Rich UI               ║
╚══════════════════════════════════════════════════════════╝[/bold magenta]
"""


def fetch_single_credential(client: httpx.Client, access_token: str, server: Dict, country_code: str) -> Optional[Dict]:
    """Fetch credentials for a single server"""
    signature = server.get("signature")
    if not signature:
        return None

    cred_url = "https://api-pro.falais.com/rest/v1/security/tokens/accs-proxy"
    headers_cred = {**HEADERS_VPN, "authorization": f"Bearer {access_token}"}

    try:
        r = client.post(cred_url,
            json={
                "type": "accs-proxy",
                "clientApp": {"name": "URBAN_VPN_BROWSER_EXTENSION"},
                "signature": signature
            },
            headers=headers_cred,
            timeout=15)
        r.raise_for_status()
        proxy_data = r.json()

        ip = server.get("address", {}).get("primary", {}).get("ip", "")
        port = server.get("address", {}).get("primary", {}).get("port", "")
        user = proxy_data["value"]
        passwd = proxy_data["value"]

        if ip and port:
            proxy_url = f"http://{user}:{passwd}@{ip}:{port}"
            return {
                "url": proxy_url,
                "ip": ip,
                "port": str(port),
                "user": user,
                "pass": passwd,
                "country": country_code,
            }
    except Exception:
        pass
    return None


def fetch_urban_vpn_proxies(progress_callback: Optional[Callable] = None) -> List[Dict]:
    """Fetch fresh proxies from Urban VPN API with parallel credential fetching"""
    new_proxies = []

    try:
        with httpx.Client(timeout=TIMEOUT, verify=False) as client:
            # Step 1: Anonymous token
            if progress_callback:
                progress_callback("status", "Getting anonymous token...")
            
            anon_url = ("https://api-pro.falais.com/rest/v1/registrations/clientApps"
                       "/URBAN_VPN_BROWSER_EXTENSION/users/anonymous")
            r = client.post(anon_url,
                json={"clientApp": {"name": "URBAN_VPN_BROWSER_EXTENSION", "browser": "CHROME"}},
                headers=HEADERS_VPN)
            r.raise_for_status()
            anon_token = r.json()["value"]

            # Step 2: Access token
            if progress_callback:
                progress_callback("status", "Getting access token...")
            
            acc_url = "https://api-pro.falais.com/rest/v1/security/tokens/accs"
            headers_auth = {**HEADERS_VPN, "authorization": f"Bearer {anon_token}"}
            r = client.post(acc_url,
                json={"type": "accs", "clientApp": {"name": "URBAN_VPN_BROWSER_EXTENSION"}},
                headers=headers_auth)
            r.raise_for_status()
            access_token = r.json()["value"]

            # Step 3: Server list
            if progress_callback:
                progress_callback("status", "Fetching server list...")
            
            countries_url = "https://stats.falais.com/api/rest/v2/entrypoints/countries"
            headers_countries = {
                "accept": "application/json",
                "accept-language": "en-US,en;q=0.9",
                "authorization": f"Bearer {access_token}",
                "user-agent": HEADERS_VPN["user-agent"],
                "x-client-app": "URBAN_VPN_BROWSER_EXTENSION",
            }
            r = client.get(countries_url, headers=headers_countries)
            r.raise_for_status()
            countries_data = r.json()

            countries = countries_data.get("countries", {}).get("elements", [])
            all_servers = []
            
            for country in countries:
                cc = country.get("code", {}).get("iso2", "??")
                country_name = country.get("name", cc)
                for server in country.get("servers", {}).get("elements", []):
                    all_servers.append((server, cc, country_name))

            total_servers = len(all_servers)
            
            if progress_callback:
                progress_callback("total", total_servers)
                progress_callback("status", f"Fetching credentials from {total_servers} servers...")

            # Step 4: Parallel credential fetching
            fetched_lock = threading.Lock()
            progress_data = {
                "done": 0,
                "ok": 0,
                "fail": 0,
                "results": []
            }

            def fetch_one(args):
                server, cc, country_name = args
                result = fetch_single_credential(client, access_token, server, cc)
                with fetched_lock:
                    progress_data["done"] += 1
                    if result:
                        progress_data["ok"] += 1
                        progress_data["results"].append(result)
                    else:
                        progress_data["fail"] += 1
                    
                    if progress_callback:
                        progress_callback("progress", progress_data["done"], total_servers, 
                                        progress_data["ok"], progress_data["fail"])
                return result

            # Use ThreadPoolExecutor for parallel fetching
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [executor.submit(fetch_one, server_data) for server_data in all_servers]
                for future in as_completed(futures):
                    pass  # Just wait for completion, results are collected in progress_data

            new_proxies = progress_data["results"]
            
            if progress_callback:
                progress_callback("complete", len(new_proxies), total_servers, 
                                progress_data["ok"], progress_data["fail"])
                
    except Exception as e:
        if progress_callback:
            progress_callback("error", str(e))
        else:
            console.print(f"\n[red]✗ Error: {e}[/red]")
        return []

    return new_proxies


def save_proxies_to_file(proxies: List[Dict], filename: str = None):
    """Save proxies to file in various formats"""
    if not filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"sukuna_proxies_{timestamp}.txt"
    
    with open(filename, 'w') as f:
        for p in proxies:
            f.write(f"{p['ip']}:{p['port']}:{p['user']}:{p['pass']}\n")
    
    return filename




if __name__ == "__main__":
    proxies = fetch_urban_vpn_proxies()
    print(f"Fetched {len(proxies)} proxies")
