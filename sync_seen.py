#!/usr/bin/env python3
"""Write seen.json, for the site's Unseen and Watchlist pills.

The Streaming site keeps the user's Letterboxd films as TMDB ids (watched.json and
watchlist.json). This site knows its films by Letterboxd slug, so each film now
showing is matched to its TMDB id (read off its Letterboxd page, remembered in
tmdb_ids.json) and seen.json lists the slugs of those that are watched or on the
watchlist.

Usage: python3 sync_seen.py [SOURCE]

SOURCE is the folder or URL holding watched.json and watchlist.json. By default
the neighbouring ../Streaming folder if there is one, else the published
Streaming site (which is what the daily scrape uses).
"""

import datetime as dt
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLISHED = "https://barburevencu.github.io/streaming-movies"
UA = "paris-cinemas (github.com/barburevencu/paris-cinemas)"
SLUG = re.compile(r"/film/([^/]+)/")
TMDB_ID = re.compile(r'data-tmdb-type="movie"\s+data-tmdb-id="(\d+)"')


def read(source, name):
    if source.startswith("http"):
        req = urllib.request.Request(f"{source.rstrip('/')}/{name}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    return json.loads((Path(source).expanduser() / name).read_text())


def tmdb_id(slug):
    """TMDB id of a Letterboxd film (None for a TV entry or a page that won't load)."""
    req = urllib.request.Request(f"https://letterboxd.com/film/{slug}/", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            m = TMDB_ID.search(resp.read().decode("utf-8", "replace"))
    except OSError as e:
        print(f"  ! {slug}: {e}", file=sys.stderr)
        return None
    return int(m.group(1)) if m else None


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else str(HERE.parent / "Streaming")
    if len(sys.argv) < 2 and not Path(source).is_dir():
        source = PUBLISHED
    watched = set(filter(None, read(source, "watched.json")["films"].values()))
    listed = read(source, "watchlist.json")["films"]
    watchlist = set(filter(None, listed.values()))

    data = json.loads((HERE / "data.json").read_text())
    slugs = sorted({m.group(1) for r in data["rows"] if (m := SLUG.search(r.get("Letterboxd") or ""))})

    cache_file = HERE / "tmdb_ids.json"
    ids = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    ids.update({s: i for s, i in listed.items() if i})  # the watchlist already knows its films' ids
    todo = [s for s in slugs if not ids.get(s)]
    print(f"{len(slugs)} films showing, {len(todo)} to look up")
    with ThreadPoolExecutor(4) as pool:
        for s, i in zip(todo, pool.map(tmdb_id, todo)):
            if i:
                ids[s] = i
    ids = {s: ids[s] for s in slugs if ids.get(s)}  # keep only films now showing, so the file stays small
    cache_file.write_text(json.dumps(ids, indent=0) + "\n")

    out = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "watched": [s for s in slugs if ids.get(s) in watched],
           "watchlist": [s for s in slugs if ids.get(s) in watchlist]}
    (HERE / "seen.json").write_text(json.dumps(out, indent=0) + "\n")
    print(f"seen.json: {len(out['watched'])} watched, {len(out['watchlist'])} on the watchlist")


if __name__ == "__main__":
    main()
