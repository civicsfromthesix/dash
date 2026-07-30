import json
import time
import os
from datetime import datetime, timezone
from html import escape
from typing import List, Dict

import requests

# ========================= CONFIG =========================
# The token now comes from an environment variable — it never lives in
# this file. Locally: export X_BEARER_TOKEN="..."
# On GitHub: stored as a repo secret (see SETUP_GUIDE.md).
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN")

HANDLES = [
    "BradMBradford",
    "MayorOliviaChow",
]

MAX_RESULTS_PER_USER = 8
BASE_URL = "https://api.x.com/2"
CACHE_FILE = "x_cache.json"
CACHE_SECONDS = 1800  # 30 minutes
# =======================================================


def _headers() -> dict:
    if not X_BEARER_TOKEN:
        raise RuntimeError("X_BEARER_TOKEN environment variable is not set.")
    return {"Authorization": f"Bearer {X_BEARER_TOKEN}"}


def get_user_id(username: str) -> str:
    username = username.lstrip("@")
    resp = requests.get(f"{BASE_URL}/users/by/username/{username}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def fetch_recent_posts(username: str, max_results: int = 8) -> List[Dict]:
    user_id = get_user_id(username)
    handle = username.lstrip("@")

    resp = requests.get(
        f"{BASE_URL}/users/{user_id}/tweets",
        headers=_headers(),
        params={
            "max_results": max(5, min(max_results, 100)),
            "tweet.fields": "created_at,public_metrics",
            "exclude": "retweets,replies",
        },
        timeout=15,
    )
    resp.raise_for_status()

    posts = []
    for post in resp.json().get("data", []):
        metrics = post.get("public_metrics", {})
        posts.append({
            "handle": f"@{handle}",
            "text": post["text"],
            "url": f"https://x.com/{handle}/status/{post['id']}",
            "timestamp": post["created_at"][:16].replace("T", " "),
            "likes": metrics.get("like_count", 0),
            "comments": metrics.get("reply_count", 0),
        })
    return posts


def fetch_all_posts() -> Dict[str, List[Dict]]:
    """Reuses cached data if it's less than 30 minutes old, so re-running
    this script (e.g. while testing) doesn't burn API calls unnecessarily."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < CACHE_SECONDS:
                return cache["data"]
        except (json.JSONDecodeError, KeyError):
            pass

    all_data = {}
    for handle in HANDLES:
        try:
            all_data[handle.lstrip("@")] = fetch_recent_posts(handle, MAX_RESULTS_PER_USER)
        except Exception as e:
            print(f"Error @{handle}: {e}")
            all_data[handle.lstrip("@")] = []
        time.sleep(1.2)

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.time(), "data": all_data}, f, indent=2, ensure_ascii=False)

    return all_data


def generate_html() -> str:
    data = fetch_all_posts()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X Dashboard</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; background: #f4f4f4; }}
  .card {{ background: white; padding: 15px; margin: 15px 0; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
  .handle {{ font-weight: bold; color: #1DA1F2; }}
  .time {{ color: #666; font-size: 0.9em; }}
  a {{ color: #1DA1F2; }}
</style>
</head>
<body>
<h1>X Dashboard</h1>
<p>Last updated: {now} &middot; refreshes automatically every 30 minutes</p>
"""

    for handle, posts in data.items():
        page += f"<h2>@{escape(handle)}</h2>"
        if not posts:
            page += "<p>No posts available.</p>"
            continue
        for p in posts:
            page += f"""
<div class="card">
  <p><span class="handle">{escape(p['handle'])}</span> &middot; <span class="time">{escape(p['timestamp'])}</span></p>
  <p>{escape(p['text'])}</p>
  <p>&hearts; {p['likes']} &nbsp; &#128172; {p['comments']}</p>
  <a href="{p['url']}" target="_blank">View on X &rarr;</a>
</div>
"""

    page += """
<script>setTimeout(() => location.reload(), 300000);</script>
</body>
</html>
"""
    return page


if __name__ == "__main__":
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(generate_html())
    print("Dashboard generated: dashboard.html")
