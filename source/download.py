#!/usr/bin/env python3
"""Fetch and verify the DJI / RoboMaster CAD source files listed in SOURCES.json.

The files are large and the server is slow, so downloads resume (HTTP
Range) and nothing is re-fetched once the sha256 matches. Standard library
only.

  download.py                 fetch every file that is missing or wrong, then verify
  download.py fetch [NAME..]  fetch the named files (or all)
  download.py verify [NAME..] check size and sha256 of the local copies
  download.py check [NAME..]  metadata only: HEAD each URL and compare size / ETag
                              with the record, without downloading
  download.py record NAME     compute the sha256 of a local file whose record
                              still has null, and write it into SOURCES.json

Files land next to this script under their original names and are
gitignored (see NOTICE.md).
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RECORD = os.path.join(HERE, "SOURCES.json")
CHUNK = 1 << 20


def load():
    return json.load(open(RECORD, encoding="utf-8"))


def save(rec):
    json.dump(rec, open(RECORD, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    open(RECORD, "a", encoding="utf-8").write("\n")


def select(rec, names):
    files = rec["files"]
    if not names:
        return files
    known = {f["name"]: f for f in files}
    missing = [n for n in names if n not in known]
    if missing:
        sys.exit(f"not in SOURCES.json: {', '.join(missing)}")
    return [known[n] for n in names]


def sha256_of(path, progress=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def head(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, int(r.headers.get("Content-Length") or -1), (r.headers.get("ETag") or "").strip('"'), r.headers.get("Last-Modified")


def local_state(entry):
    path = os.path.join(HERE, entry["name"])
    if not os.path.exists(path):
        return path, "missing"
    size = os.path.getsize(path)
    if size < entry["bytes"]:
        return path, f"partial {size / 1e6:.0f} of {entry['bytes'] / 1e6:.0f} MB"
    if size > entry["bytes"]:
        return path, f"wrong size {size} (expected {entry['bytes']})"
    return path, "complete"


def verify(entry, quiet=False):
    path, state = local_state(entry)
    if state != "complete":
        print(f"{entry['name']}: {state}")
        return False
    if entry["sha256"] is None:
        print(f"{entry['name']}: size ok, no sha256 on record (run `download.py record {entry['name']}`)")
        return True
    t = time.time()
    got = sha256_of(path)
    ok = got == entry["sha256"]
    print(f"{entry['name']}: {'sha256 ok' if ok else 'SHA256 MISMATCH ' + got} ({time.time() - t:.0f}s)")
    return ok


def fetch(entry):
    path, state = local_state(entry)
    if state == "complete" and (entry["sha256"] is None or sha256_of(path) == entry["sha256"]):
        print(f"{entry['name']}: already complete")
        return True
    if state.startswith("wrong size") or (state == "complete"):
        print(f"{entry['name']}: local copy is {state if state != 'complete' else 'corrupt'}, refetching")
        os.remove(path)
    have = os.path.getsize(path) if os.path.exists(path) else 0
    total = entry["bytes"]
    while have < total:
        req = urllib.request.Request(entry["url"], headers={"Range": f"bytes={have}-"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "ab") as f:
                if r.status == 200 and have:
                    # server ignored the range: start over
                    f.truncate(0)
                    have = 0
                t0, t_last, at_start = time.time(), 0.0, have
                while True:
                    b = r.read(CHUNK)
                    if not b:
                        break
                    f.write(b)
                    have += len(b)
                    if time.time() - t_last > 2:
                        rate = (have - at_start) / max(time.time() - t0, 1e-9) / 1e6
                        print(f"\r{entry['name']}: {have / 1e6:.0f} / {total / 1e6:.0f} MB  {rate:.1f} MB/s", end="", flush=True)
                        t_last = time.time()
                print()
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            print(f"\n{entry['name']}: {e}; retrying in 10 s", flush=True)
            time.sleep(10)
            have = os.path.getsize(path) if os.path.exists(path) else 0
    return verify(entry)


def check(entry):
    try:
        status, size, etag, modified = head(entry["url"])
    except Exception as e:  # noqa: BLE001
        print(f"{entry['name']}: HEAD failed: {e}")
        return False
    notes = []
    if status != 200:
        notes.append(f"status {status}")
    if size != entry["bytes"]:
        notes.append(f"remote size {size} != recorded {entry['bytes']}")
    if etag and entry.get("etag") and etag != entry["etag"]:
        notes.append(f"remote ETag {etag} != recorded {entry['etag']}")
    path, state = local_state(entry)
    print(f"{entry['name']}: remote {'ok' if not notes else '; '.join(notes)}; local {state}")
    return not notes


def record(entry, rec):
    path, state = local_state(entry)
    if state != "complete":
        sys.exit(f"{entry['name']}: {state}")
    got = sha256_of(path)
    if entry["sha256"] not in (None, got):
        sys.exit(f"{entry['name']}: sha256 on record is {entry['sha256']}, local file is {got}; not overwriting")
    entry["sha256"] = got
    save(rec)
    print(f"{entry['name']}: recorded sha256 {got}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="fetch", choices=["fetch", "verify", "check", "record"])
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    rec = load()
    entries = select(rec, a.names)
    if a.command == "record":
        if len(entries) != 1 or not a.names:
            sys.exit("record takes exactly one name")
        record(entries[0], rec)
        return
    fn = {"fetch": fetch, "verify": verify, "check": check}[a.command]
    ok = all([fn(e) for e in entries])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
