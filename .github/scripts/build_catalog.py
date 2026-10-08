#!/usr/bin/env python3
"""
build_catalog.py - generates catalog.json for the add-on catalog on deklica.github.io.

Usage (the repository root is detected automatically, so the script can be run from anywhere):
    python3 .github/scripts/build_catalog.py              # update catalog.json and addons.xml.md5 files
    python3 .github/scripts/build_catalog.py --pretty     # indented JSON
    python3 .github/scripts/build_catalog.py --no-remote  # local sources only
    python3 .github/scripts/build_catalog.py --strict     # exit with status 1 if any source failed

Sources are read from the <dir> entries of the repository add-ons listed in REPOS (addon.xml inside
the newest repository zip, or the plain addon.xml next to it). Entries pointing at this repository
are read from the working tree; everything else is downloaded and marked as external.

Dates: for local add-ons the date comes from git history (first commit of the current zip), so a
full clone is required - in GitHub Actions use actions/checkout with fetch-depth: 0. For remote
add-ons the date of the current zip is taken from the GitHub API or the Last-Modified header and
remembered in catalog.json; GITHUB_TOKEN / GH_TOKEN is used for the API when present.

Requires Python 3.8+ and the standard library only.
"""

import argparse
import datetime as dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
import zipfile

warnings.filterwarnings("ignore", message="Bad certificate in Windows certificate store", category=UserWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPOS = {
    # catalog key: (display name, repository add-on id, folder with its zip)
    "dexe":   ("dEXE's Addons Repository",         "repository.dexe",   "repo/repository.dexe"),
    "roooar": ("Roooar! Repo of all Repositories", "repository.roooar", "repo/repository.roooar"),
}

# URLs that point at this repository are read from the working tree (group 1 = path in the repo)
LOCAL_URL_RE = re.compile(
    r"^https?://(?:raw\.githubusercontent\.com|github\.com)/deklica/repo\.dexe/(?:raw/)?(?:refs/heads/)?(?:master|main)/(.*)$", re.I)
# Own sources hosted elsewhere (not marked as external)
OWN_REMOTE_PREFIXES = ["https://gitfront.io/r/dexe/"]

EXCLUDE_IDS = {
    "script.module.oriontest",
    "script.module.requests",
}
PARENT_OVERRIDES = {
    # "part id": "main add-on id"
    "script.module.acctvwr": "script.module.acctmgr",
    "script.module.blackscrapers": "plugin.video.blacklodge",
    "service.lt2http": "plugin.video.elementum",
}
TYPE_OVERRIDES = {
    # "id": "type"  (video, audio, image, program, service, context, skin, subtitles, repository, module ...)
}

# Used only when the repository add-on cannot be read locally
RAW = "https://raw.githubusercontent.com/deklica/repo.dexe/master/"
FALLBACK_SOURCES = {
    "dexe":   [RAW + "repo/addons.xml", RAW + "addons.xml",
               "https://gitfront.io/r/dexe/n7TtSm9NEVFs/dexerepo/raw/addons.xml", RAW + "misc/addons.xml"],
    "roooar": [RAW + "repos/addons.xml", RAW + "repo/addons.xml"],
}

HTTP_TIMEOUT = 30
USER_AGENT = "Kodi/21.0 (build_catalog)"
NEW_VERSION_AS_UPDATE = True   # remote add-ons: if the zip date is unknown, a new version is dated with the run time
REMOTE_DATES = True            # remote add-ons: look up the publish date of the current zip

# ---------------------------------------------------------------------------
# Add-on types (Kodi conventions)
# ---------------------------------------------------------------------------
PREFIX_TYPES = [
    ("repository.", "repository"), ("skin.", "skin"), ("resource.", "resource"),
    ("service.subtitles.", "subtitles"), ("script.service.", "service"),
    ("context.", "context"),
    ("weather.", "weather"), ("pvr.", "pvr"), ("plugin.video.", "video"), ("plugin.audio.", "audio"),
    ("plugin.image.", "image"), ("plugin.game.", "game"), ("plugin.program.", "program"), ("service.", "service"),
    ("metadata.", "scraper"), ("screensaver.", "screensaver"), ("visualization.", "visualization"),
    ("inputstream.", "inputstream"),
]

PROVIDES_MAP = {"video": "video", "audio": "audio", "image": "image", "executable": "program", "game": "game"}

# Extension points in priority order; None = type comes from <provides>
POINT_MAP = [
    ("xbmc.gui.skin", "skin"),
    ("xbmc.addon.repository", "repository"),
    ("xbmc.pvrclient", "pvr"),
    ("kodi.pvrclient", "pvr"),
    ("xbmc.python.pluginsource", None),
    ("xbmc.subtitle.module", "subtitles"),
    ("xbmc.python.weather", "weather"),
    ("xbmc.python.lyrics", "lyrics"),
    ("xbmc.ui.screensaver", "screensaver"),
    ("xbmc.player.musicviz", "visualization"),
    ("kodi.inputstream", "inputstream"),
    ("kodi.gameclient", "game"),
    ("xbmc.metadata.scraper", "scraper"),
    ("xbmc.python.script", None),
    ("xbmc.service", "service"),
    ("kodi.context.item", "context"),
    ("kodi.resource", "resource"),
    ("xbmc.python.module", "module"),
    ("xbmc.python.library", "module"),
]

# Types shown under "modules and parts" instead of as stand-alone add-ons
DEPENDENCY_TYPES = {"module"}

TAG_RE = re.compile(r"\[/?(?:COLOR[^\]]*|B|I|UPPERCASE|LOWERCASE|CAPITALIZE|LIGHT|CR)\]", re.I)
ADDON_BLOCK_RE = re.compile(r"<addon\b.*?</addon>", re.S)
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
SECTION_RE = re.compile(r"^=+\s*(.*?)\s*=+$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
DIR_OR_COMMENT_RE = re.compile(r"<!--(.*?)-->|<dir\b[^>]*>(.*?)</dir>", re.S)

GUI_TO_KODI = {"5.14": 18, "5.15": 19, "5.16": 20, "5.17": 21, "5.18": 22}
SUFFIX_TO_KODI = {"leia": 18, "matrix": 19, "nexus": 20, "omega": 21, "piers": 22}

GH_RAW_RE = re.compile(r"^https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/(?:refs/heads/)?([^/]+)/(.+)$")
GH_BLOB_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/raw/(?:refs/heads/)?([^/]+)/(.+)$")
_gh_state = {"limited": False, "calls": 0}


def log(msg=""):
    print(msg, file=sys.stderr)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def version_key(v):
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.\-~+]", v or "0")]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def clean_label(text):
    t = re.sub(r"\s+", " ", text or "").strip(" -=")
    return re.sub(r"\s+v?\d+(?:\.\d+)+[a-z]?$", "", t)


def classify(url):
    m = LOCAL_URL_RE.match(url)
    if m:
        return "local", m.group(1)
    if any(url.startswith(p) for p in OWN_REMOTE_PREFIXES):
        return "own-remote", url
    return "external", url


def repository_addon_xml(root, addon_id, folder):
    """addon.xml of a repository add-on: from the newest zip, else the plain file. Returns (text, source path)."""
    full = os.path.join(root, folder)
    zips = []
    if os.path.isdir(full):
        for fn in os.listdir(full):
            m = re.match(re.escape(addon_id) + r"-(.+)\.zip$", fn)
            if m:
                zips.append((version_key(m.group(1)), fn))
    for _, fn in sorted(zips, reverse=True):
        try:
            with zipfile.ZipFile(os.path.join(full, fn)) as z:
                name = next((n for n in z.namelist() if n.lower() == f"{addon_id}/addon.xml".lower()), None)
                if name:
                    return z.read(name).decode("utf-8", "replace"), f"{folder}/{fn}"
        except (zipfile.BadZipFile, OSError) as e:
            log(f"  warning: cannot open {folder}/{fn}: {e}")
    plain = os.path.join(full, "addon.xml")
    if os.path.isfile(plain):
        with open(plain, encoding="utf-8", errors="replace") as f:
            return f.read(), f"{folder}/addon.xml"
    return None, None


def sources_for(repo_key, root):
    """Source list ({url, kind, path, folder, datadir, label, kodi_min, kodi_max}) from the <dir> entries."""
    _, addon_id, folder = REPOS[repo_key]
    text, rel = repository_addon_xml(root, addon_id, folder)
    out = []
    if text:
        label = None
        for m in DIR_OR_COMMENT_RE.finditer(text):
            if m.group(1) is not None:                       # comment = name of the next external repository
                c = clean_label(m.group(1))
                label = c if c and c.lower() not in ("repositories", "repos") else label
                continue
            body = m.group(2)
            info = re.search(r"<info\b[^>]*>(.*?)</info>", body, re.S)
            if not info:
                continue
            url = info.group(1).strip()
            dd = re.search(r"<datadir\b[^>]*>(.*?)</datadir>", body, re.S)
            datadir = dd.group(1).strip() if dd else url.rsplit("/", 1)[0] + "/"
            head = re.match(r"<dir\b[^>]*>", m.group(0)).group(0)
            kmin = re.search(r'minversion="([^"]+)"', head)
            kmax = re.search(r'maxversion="([^"]+)"', head)
            kind, path = classify(url)
            dkind, dpath = classify(datadir)
            out.append({
                "url": url, "kind": kind, "path": path if kind == "local" else None,
                "folder": (dpath.strip("/") or ".") if dkind == "local" else None,
                "datadir": datadir if datadir.endswith("/") else datadir + "/",
                "label": label if kind == "external" else None,
                "kodi_min": kmin.group(1) if kmin else None,
                "kodi_max": kmax.group(1) if kmax else None,
            })
        log(f"[{repo_key}] {len(out)} sources from {rel}")
    else:
        log(f"[{repo_key}] warning: {addon_id} not found in {folder}, using fallback sources")
        for url in FALLBACK_SOURCES.get(repo_key, []):
            kind, path = classify(url)
            folder = {"addons.xml": "zips"}.get(path, path.rsplit("/", 1)[0] if path and "/" in path else None)
            out.append({"url": url, "kind": kind, "path": path if kind == "local" else None, "folder": folder,
                        "datadir": RAW + folder + "/" if folder else url.rsplit("/", 1)[0] + "/",
                        "label": None, "kodi_min": None, "kodi_max": None})
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", "replace")


def read_text(src, root, allow_remote):
    if src["kind"] == "local":
        full = os.path.join(root, src["path"])
        if not os.path.isfile(full):
            return None, "file not found"
        with open(full, encoding="utf-8", errors="replace") as f:
            return f.read(), None
    if not allow_remote:
        return None, "skipped (--no-remote)"
    try:
        return fetch(src["url"]), None
    except Exception as e:
        return None, str(e)[:120]


# ---------------------------------------------------------------------------
# Publish date of a remote zip
# ---------------------------------------------------------------------------
def github_commit_date(owner, repo, branch, path):
    if _gh_state["limited"]:
        return None
    q = urllib.parse.urlencode({"path": path, "sha": branch, "per_page": 1})
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}/commits?{q}",
                                 headers={"User-Agent": "build_catalog", "Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        _gh_state["calls"] += 1
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data:
            return data[0]["commit"]["committer"]["date"]
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            _gh_state["limited"] = True
            log(f"  warning: GitHub API rate limit reached (HTTP {e.code}); remaining dates fall back to version changes")
    except Exception:
        pass
    return None


def last_modified(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            lm = r.headers.get("Last-Modified")
        if lm:
            return email.utils.parsedate_to_datetime(lm).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    return None


def remote_zip_date(datadir, aid, version):
    url = f"{datadir}{aid}/{aid}-{version}.zip"
    for rx in (GH_RAW_RE, GH_BLOB_RE):
        m = rx.match(url)
        if m:
            owner, repo, branch, path = m.groups()
            return github_commit_date(owner, repo, branch, urllib.parse.unquote(path))
    return last_modified(url)


# ---------------------------------------------------------------------------
# Index comment (sections, parent/child, notes) at the top of local addons.xml files
# ---------------------------------------------------------------------------
def parse_index_comment(text):
    info = {}
    for m in COMMENT_RE.finditer(text):
        body = m.group(1)
        if "<addon" in body:
            continue
        section = None
        stack = []
        for raw in body.splitlines():
            line = raw.rstrip()
            if not line.strip():
                stack = []
                continue
            s = line.strip()
            sm = SECTION_RE.match(s)
            if sm or s.startswith("==="):
                section = (sm.group(1) if sm else "").strip() or None
                stack = []
                continue
            indent = len(line) - len(line.lstrip(" \t"))
            token, _, rest = s.partition(" ")
            if not ID_RE.match(token) or "." not in token:
                continue
            note = rest.strip().strip("()").lstrip("-").strip() or None
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else None
            stack.append((indent, token))
            info.setdefault(token, {"section": section, "parent": parent, "note": note})
    return info


# ---------------------------------------------------------------------------
# Add-on entries
# ---------------------------------------------------------------------------
def clean_name(name):
    name = TAG_RE.sub(lambda m: " " if m.group(0).upper() == "[CR]" else "", name or "")
    return re.sub(r"\s+", " ", name).strip()


def parse_block(block):
    try:
        el = ET.fromstring(block)
    except ET.ParseError:
        head = re.match(r"<addon\b[^>]*>", block, re.S).group(0)
        attr = lambda k: (re.search(rf'\s{k}="([^"]*)"', head) or [None, None])[1]
        points = re.findall(r'<extension\b[^>]*point="([^"]+)"', block)
        provides = re.findall(r"<provides>([^<]*)</provides>", block)
        icon = re.search(r"<icon>([^<]*)</icon>", block)
        plat = re.search(r"<platform>([^<]*)</platform>", block)
        reqs = [(m.group(1), 'optional="true"' in m.group(0),
                 (re.search(r'version="([^"]+)"', m.group(0)) or [None, None])[1])
                for m in re.finditer(r'<import\b[^>]*addon="([^"]+)"[^>]*>', block)]
        return {"id": attr("id"), "name": attr("name"), "version": attr("version"),
                "author": attr("provider-name"), "points": [(p, " ".join(provides)) for p in points],
                "icon": icon.group(1).strip() if icon else "icon.png",
                "platform": plat.group(1).strip() if plat else None, "broken": "<broken" in block,
                "requires": reqs}
    points, icon, platform, broken = [], None, None, False
    for ext in el.findall("extension"):
        point = ext.get("point", "")
        provides = " ".join((p.text or "").strip() for p in ext.findall("provides"))
        points.append((point, provides))
        if point in ("xbmc.addon.metadata", "kodi.addon.metadata"):
            ic = ext.find("assets/icon")
            if ic is not None and (ic.text or "").strip():
                icon = ic.text.strip()
            pl = ext.find("platform")
            if pl is not None and (pl.text or "").strip():
                platform = pl.text.strip()
            if ext.find("broken") is not None:
                broken = True
    reqs = [(imp.get("addon"), (imp.get("optional") or "").lower() == "true", imp.get("version"))
            for imp in el.findall("requires/import") if imp.get("addon")]
    return {"id": el.get("id"), "name": el.get("name"), "version": el.get("version"),
            "author": el.get("provider-name"), "points": points,
            "icon": icon or "icon.png",
            "platform": platform, "broken": broken, "requires": reqs}


def kodi_types(points, addon_id=""):
    """Add-on types, main type first."""
    types = []
    for prefix, t in POINT_MAP:
        for point, provides in points:
            if not point.startswith(prefix):
                continue
            if t:
                found = [t]
            else:
                found = [PROVIDES_MAP[p] for p in provides.split() if p in PROVIDES_MAP]
                if not found:
                    found = [] if prefix == "xbmc.python.pluginsource" else ["program"]
            for f in found:
                if f not in types:
                    types.append(f)
    if addon_id.startswith("script.") and not addon_id.startswith(("script.module.", "script.service.")) \
            and "program" in types and types[0] in ("video", "audio", "image"):
        types.remove("program")
        types.insert(0, "program")
    # Kodi takes the main type from the first extension point
    first = next((p for p, prov in points if p not in ("xbmc.addon.metadata", "kodi.addon.metadata")
                  and not (p == "xbmc.python.pluginsource" and not any(x in PROVIDES_MAP for x in prov.split()))), None)
    if first == "xbmc.service" and "service" in types and types[0] != "service":
        types.remove("service")
        types.insert(0, "service")
    if ".helper" in addon_id and "service" in types and types[0] != "service":
        types.remove("service")
        types.insert(0, "service")
    for prefix, t in PREFIX_TYPES:
        if addon_id.startswith(prefix):
            if t in types:
                types.remove(t)
                types.insert(0, t)
            elif not types or types == ["module"]:
                types.insert(0, t)
            break
    return types or ["other"]


# ---------------------------------------------------------------------------
# Supported Kodi versions: (min, max), max None = "and newer"
# ---------------------------------------------------------------------------
def _major_minor(v):
    m = re.match(r"(\d+)(?:\.(\d+))?", v or "")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (None, None)


def kodi_from_addon(aid, version, imports):
    lo, hi = None, None

    def at_least(k):
        nonlocal lo
        lo = k if lo is None else max(lo, k)

    def at_most(k):
        nonlocal hi
        hi = k if hi is None else min(hi, k)

    for dep, optional, ver in imports:
        if optional or not ver:
            continue
        major, minor = _major_minor(ver)
        if major is None:
            continue
        if dep == "xbmc.python":
            if major >= 3:
                at_least(20 if version_key(ver) >= version_key("3.0.1") else 19)
            else:
                at_most(18)
        elif dep == "xbmc.gui":
            k = GUI_TO_KODI.get(f"{major}.{minor}")
            if k:
                at_least(k); at_most(k)
        elif dep == "xbmc.addon" and major >= 17:
            at_least(major)
    low = (version or "").lower()
    for name, k in SUFFIX_TO_KODI.items():
        if name in low:
            at_least(k)
    if aid.startswith(("pvr.", "inputstream.", "audiodecoder.", "visualization.", "screensaver.", "imagedecoder.")):
        major, _ = _major_minor(version)
        if major and 19 <= major <= 30:
            at_least(major); at_most(major)
    return lo, hi


def kodi_from_dir(vmin, vmax):
    """<dir minversion/maxversion>; x.9 is the alpha of the next major version."""
    lo = hi = None
    if vmin:
        major, minor = _major_minor(vmin)
        if major:
            lo = major + 1 if minor >= 9 else major
    if vmax:
        major, _ = _major_minor(vmax)
        if major:
            hi = major
    return lo, hi


def ranges_overlap(a, b):
    lo = max(x for x in (a[0], b[0], 0) if x is not None)
    his = [x for x in (a[1], b[1]) if x is not None]
    return not his or lo <= min(his)


def range_union(a, b):
    lo = None if a[0] is None or b[0] is None else min(a[0], b[0])
    hi = None if a[1] is None or b[1] is None else max(a[1], b[1])
    return (lo, hi)


def kodi_range(parts):
    lo, hi = None, None
    for a, b in parts:
        if a is not None:
            lo = a if lo is None else max(lo, a)
        if b is not None:
            hi = b if hi is None else min(hi, b)
    if lo is not None and hi is not None and lo > hi:
        # add-on and <dir> range contradict each other: trust the add-on for Python 2 add-ons, else the directory
        own = parts[0] if parts else (None, None)
        if own[1] is not None and own[1] <= 18:
            return own
        dirs = [p for p in parts[1:] if p != (None, None)]
        return dirs[0] if dirs else own
    return lo, hi


def kodi_label(rows, src):
    per_row = [kodi_from_addon(r["id"], r["version"], r.get("requires", [])) for r in rows]
    los = [a for a, _ in per_row if a is not None]
    his = [b for _, b in per_row]
    lo = min(los) if los else None
    hi = None if (not his or any(b is None for b in his)) else max(his)
    lo, hi = kodi_range([(lo, hi), kodi_from_dir(src.get("kodi_min"), src.get("kodi_max"))])
    if lo is None and hi is None:
        return None
    return {"min": lo, "max": hi}


def kodi_label_multi(items):
    labels = [kodi_label(rows, src) for rows, src in items]
    if not labels or any(l is None for l in labels):
        return None
    lo = None if any(l["min"] is None for l in labels) else min(l["min"] for l in labels)
    hi = None if any(l["max"] is None for l in labels) else max(l["max"] for l in labels)
    if lo is None and hi is None:
        return None
    return {"min": lo, "max": hi}


# ---------------------------------------------------------------------------
# Dates from git history (local sources)
# ---------------------------------------------------------------------------
def git_dates(root, dirs):
    """added: path -> date added; touched: folder/id -> last change; first: folder/id -> first appearance."""
    added, touched, first = {}, {}, {}
    if not dirs:
        return added, touched, first
    try:
        out = subprocess.run(["git", "-C", root, "log", "--format=%x00%cI", "--name-status", "--no-renames", "--", *dirs],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        log(f"  warning: git log failed ({e}); using file modification times")
        return None, None, None
    date = None
    for line in out.splitlines():
        if line.startswith("\x00"):
            date = line[1:].strip()
            continue
        if not line.strip() or date is None:
            continue
        status, _, path = line.partition("\t")
        parts = path.split("/")
        if len(parts) >= 2:
            touched.setdefault("/".join(parts[:2]), date)
        if status.startswith("A"):
            added.setdefault(path, date)
            if len(parts) >= 3:
                first["/".join(parts[:2])] = date
            elif len(parts) == 2 and parts[1].endswith(".zip") and "-" in parts[1]:
                first[parts[0] + "/" + parts[1].rsplit("-", 1)[0] + "-"] = date
    return added, touched, first


def mtime_iso(path):
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def local_date(root, folder, aid, versions, added, touched):
    best = None
    for v in versions:
        for rel in (f"{folder}/{aid}/{aid}-{v}.zip", f"{folder}/{aid}-{v}.zip"):
            d = added.get(rel) if added is not None else None
            if d is None and os.path.exists(os.path.join(root, rel)):
                d = mtime_iso(os.path.join(root, rel))     # present on disk but not committed yet
            if d and (best is None or d > best):
                best = d
    if best:
        return best
    rel = f"{folder}/{aid}"
    return touched.get(rel) if touched is not None else mtime_iso(os.path.join(root, rel))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def load_previous(path):
    """Returns (per add-on summary, full entries per catalog) from the previous catalog.json."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        summary = {(rk, a["id"]): {"version": a.get("version"), "updated": a.get("updated"),
                                   "added": a.get("added"), "has_added": "added" in a}
                   for rk, r in data.get("repos", {}).items() for a in r.get("addons", [])}
        entries = {rk: list(r.get("addons", [])) for rk, r in data.get("repos", {}).items()}
        return summary, entries
    except (OSError, ValueError, KeyError, TypeError):
        return {}, {}


def build(root, allow_remote, previous, prev_entries):
    run_time = now_iso()
    all_sources = {rk: sources_for(rk, root) for rk in REPOS}
    local_dirs = sorted({s["folder"] for ss in all_sources.values() for s in ss
                         if s["kind"] == "local" and s.get("folder") and s["folder"] != "."})
    added, touched, first_git = git_dates(root, local_dirs)
    prev_knows_added = {rk for (rk, _), p in previous.items() if p["has_added"]}
    new_addons = []
    text_cache = {}
    catalog = {"generated": run_time, "repos": {}}
    report = []
    report_dups = []
    report_kept = []
    remote_dates = [0]

    for rk, sources in all_sources.items():
        groups = {}            # (id, source index) -> entries
        index = {}
        for i, src in enumerate(sources):
            key = src["url"]
            if key not in text_cache:
                text_cache[key] = read_text(src, root, allow_remote)
            text, err = text_cache[key]
            where = src["path"] if src["kind"] == "local" else src["url"]
            origin = {"local": "local", "own-remote": "own (remote)", "external": "external"}[src["kind"]]
            if text is None:
                report.append((rk, origin, src["label"] or "", where, None, err))
                src["failed"] = True
                continue
            if src["kind"] != "external":
                for k, v in parse_index_comment(text).items():
                    index.setdefault(k, v)
            count = 0
            for block in ADDON_BLOCK_RE.findall(COMMENT_RE.sub("", text)):
                a = parse_block(block)
                if not a.get("id"):
                    continue
                count += 1
                g = groups.setdefault((a["id"], i), {"src": src, "rows": []})
                g["rows"].append(a)
            report.append((rk, origin, src["label"] or "", where, count, None))

        # The same id may exist in several sources and versions. Versions whose Kodi ranges overlap form one
        # entry (highest version wins, own source on a tie); versions for different Kodi releases stay separate.
        by_aid = {}
        for (aid, i), g in groups.items():
            if aid in EXCLUDE_IDS:
                continue
            for r in g["rows"]:
                rng = kodi_range([kodi_from_addon(r["id"], r["version"], r.get("requires", [])),
                                  kodi_from_dir(g["src"].get("kodi_min"), g["src"].get("kodi_max"))])
                by_aid.setdefault(aid, []).append((i, g, r, rng))

        variants = []
        for aid, items in by_aid.items():
            items.sort(key=lambda x: version_key(x[2]["version"] or "0"), reverse=True)
            clusters = []
            for i, g, r, rng in items:
                ver = r["version"] or "0"
                for cl in clusters:
                    same = any((x["version"] or "0") == ver for _, xs in cl[1].values() for x in xs)
                    if same or aid.startswith("repository.") or ranges_overlap(cl[0], rng):
                        cl[0] = range_union(cl[0], rng)
                        cl[1].setdefault(i, (g, []))[1].append(r)
                        break
                else:
                    clusters.append([rng, {i: (g, [r])}])
            for cl in clusters:
                variants.append((aid, list(cl[1].values()), len(clusters) > 1))

        out = []
        for aid, cgroups, split in variants:
            ranked = []
            for g, rows_ in cgroups:
                latest_g = max((r["version"] or "0" for r in rows_), key=version_key)
                ranked.append(((version_key(latest_g), 0 if g["src"]["kind"] == "external" else 1), g, rows_, latest_g))
            ranked.sort(key=lambda x: x[0], reverse=True)
            _, g, rows, latest = ranked[0]
            src = g["src"]
            if len(ranked) > 1 and not split:
                kinds = [x[1]["src"] for x in ranked]
                if any(k["kind"] != "external" for k in kinds) and src["kind"] == "external":
                    desc = lambda v, s_: f"{v} ({s_['label'] or (s_['path'] if s_['kind'] == 'local' else s_['url'])})"
                    report_dups.append((rk, aid, [desc(x[3], x[1]["src"]) for x in ranked], desc(latest, src)))
            versions = sorted({r["version"] or "0" for r in rows}, key=version_key)
            row = next(r for r in rows if (r["version"] or "0") == latest)
            bases = {v.split("+")[0] for v in versions}
            shown = latest.split("+")[0] if len(versions) > 1 and len(bases) == 1 else latest
            types = kodi_types([p for r in rows for p in r["points"]], aid)
            if aid in TYPE_OVERRIDES:
                types = [TYPE_OVERRIDES[aid]] + [t for t in types if t != TYPE_OVERRIDES[aid]]
            meta = index.get(aid, {}) if src["kind"] != "external" else {}
            icon = next((r["icon"] for r in rows if r["icon"]), None)
            platforms = []
            for r in rows:
                for p in (r["platform"] or "").split():
                    if p != "all" and p not in platforms:
                        platforms.append(p)

            if src["kind"] == "local":
                updated = local_date(root, src.get("folder") or ".", aid, versions, added, touched)
            else:
                prev = previous.get((rk, aid)) or {}
                prev_ver, prev_date = prev.get("version"), prev.get("updated")
                if prev_ver == shown and prev_date:
                    updated = prev_date
                else:
                    updated = None
                    if REMOTE_DATES and allow_remote:
                        updated = remote_zip_date(src["datadir"], aid, latest)
                        remote_dates[0] += 1 if updated else 0
                    if not updated:
                        if prev_ver is None:
                            updated = prev_date
                        elif prev_ver != shown and NEW_VERSION_AS_UPDATE:
                            updated = run_time
                        else:
                            updated = prev_date

            # first appearance: local from git, remote from the previous catalog
            prev = previous.get((rk, aid)) or {}
            first = None
            if src["kind"] == "local" and first_git:
                folder = src.get("folder") or "."
                first = first_git.get(f"{folder}/{aid}") or first_git.get(f"{folder}/{aid}-")
            if not first:
                if prev.get("has_added"):
                    first = prev.get("added")
                elif not prev and rk in prev_knows_added:
                    first = run_time
            if not prev and rk in prev_knows_added:
                new_addons.append((rk, aid, latest, src["label"] or src.get("path") or src.get("url")))

            same_version = [x for x in ranked if version_key(x[3]) == version_key(latest)
                            and (src["kind"] == "external" or x[1]["src"]["kind"] != "external")]
            out.append({
                "id": aid,
                "name": clean_name(row["name"]) or aid,
                "version": shown,
                "author": clean_name(row["author"]) or None,
                "type": types[0],
                "types": types,
                "dependency": types[0] in DEPENDENCY_TYPES or bool(meta.get("parent")),
                "parent": PARENT_OVERRIDES.get(aid) or meta.get("parent"),
                "section": meta.get("section"),
                "note": meta.get("note"),
                "platforms": platforms,
                "broken": any(r["broken"] for r in rows) or "broken" in (meta.get("note") or "").lower(),
                "updated": updated,
                "added": first,
                "icon": (src["datadir"] + aid + "/" + icon) if icon else None,
                "external": src["kind"] == "external",
                "origin": src["label"] if src["kind"] == "external" else None,
                "source": {"local": rk, "own-remote": "gitfront", "external": "external"}[src["kind"]],
                # repository add-ons: range from their own addon.xml only (the <dir> range applies to the content)
                "kodi": (kodi_label_multi([(rows, {})]) if aid.startswith("repository.") else
                         kodi_label_multi([(x[2], x[1]["src"]) for x in same_version])),
                "_requires": sorted({d for r in rows for d, opt, _ in r.get("requires", []) if not opt}),
            })

        ids = {x["id"] for x in out}
        types_by_id = {x["id"]: x["type"] for x in out}
        importers = {}
        for x in out:
            for dep in x.pop("_requires"):
                if dep in ids and dep != x["id"]:
                    importers.setdefault(dep, set()).add(x["id"])
        for x in out:
            if x["parent"] not in ids:
                x["parent"] = None
            # a helper/module required by exactly one catalog add-on is treated as its part
            users = importers.get(x["id"], set())
            if not x["parent"] and len(users) == 1 and (".helper" in x["id"] or x["id"].startswith("script.module.")):
                user = next(iter(users))
                if types_by_id.get(user) not in DEPENDENCY_TYPES:
                    x["parent"] = user
            x["dependency"] = x["type"] in DEPENDENCY_TYPES or bool(x["parent"])
        # unreadable remote source: keep its entries from the previous catalog instead of dropping them
        src_key = lambda s: s["label"] if s["kind"] == "external" else "gitfront"
        failed = {src_key(s) for s in sources if s["kind"] != "local" and s.get("failed")}
        failed -= {src_key(s) for s in sources if s["kind"] != "local" and not s.get("failed")}
        if failed:
            kept = 0
            for e in prev_entries.get(rk, []):
                key = e.get("origin") if e.get("external") else e.get("source")
                if key in failed and e["id"] not in ids and not any(x["id"] == e["id"] for x in out):
                    e = dict(e)
                    e.pop("children", None)
                    out.append(e)
                    kept += 1
            if kept:
                ids = {x["id"] for x in out}
                for x in out:
                    if x["parent"] not in ids:
                        x["parent"] = None
                report_kept.append((rk, kept, sorted(failed)))
        out.sort(key=lambda x: x["name"].lower())
        out.sort(key=lambda x: x["updated"] or "", reverse=True)
        children = {}
        for x in out:
            if x["parent"]:
                children.setdefault(x["parent"], []).append(x["id"])
        for x in out:
            x["children"] = children.get(x["id"], [])
        catalog["repos"][rk] = {"name": REPOS[rk][0], "count": len(out), "addons": out}
    if REMOTE_DATES and allow_remote:
        log(f"Remote zip dates resolved: {remote_dates[0]} (GitHub API calls: {_gh_state['calls']}"
            f"{', rate limited' if _gh_state['limited'] else ''})")
    return catalog, (report, report_dups, new_addons, report_kept)


def print_report(catalog, reports):
    report, dups, new_addons, kept = reports
    log()
    log("Sources")
    log("=" * 78)
    for rk in catalog["repos"]:
        log(f"[{rk}] {catalog['repos'][rk]['name']}")
        for r, origin, label, where, count, err in report:
            if r != rk:
                continue
            name = f" {label}" if label else ""
            status = f"{count:>4} entries" if count is not None else f"ERROR: {err}"
            log(f"  {origin:<13}{name}".rstrip())
            log(f"      {where}")
            log(f"      {status}")
        addons = catalog["repos"][rk]["addons"]
        own = sum(1 for a in addons if not a["external"])
        log(f"  -> {len(addons)} add-ons ({own} own, {len(addons) - own} external)")
        fresh = [n for n in new_addons if n[0] == rk]
        if fresh:
            log(f"  + new since previous run ({len(fresh)}):")
            for _, aid, ver, where in fresh:
                log(f"      {aid} {ver}  ({where})")
        for _, n, labels in [k for k in kept if k[0] == rk]:
            log(f"  ~ {n} entries kept from the previous catalog (source unavailable: {', '.join(labels)})")
        mine = [d for d in dups if d[0] == rk]
        if mine:
            log("  ! own add-on superseded by a newer external version:")
            for _, aid, all_v, win in mine:
                log(f"      {aid}: {', '.join(all_v)}  ->  {win}")
        log("-" * 78)


def update_md5(root):
    """Write addons.xml.md5 (32 hex characters, no newline) next to each local addons.xml when it changed."""
    try:
        autocrlf = subprocess.run(["git", "-C", root, "config", "core.autocrlf"],
                                  capture_output=True, text=True).stdout.strip().lower()
    except OSError:
        autocrlf = ""
    paths = sorted({s["path"] for rk in REPOS for s in sources_for(rk, root)
                    if s["kind"] == "local" and s.get("path") and s["path"].endswith(".xml")})
    result = []
    for rel in paths:
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            data = f.read()
        if autocrlf == "true":
            data = data.replace(b"\r\n", b"\n")      # hash what git stores (LF)
        digest = hashlib.md5(data).hexdigest()
        md5_path = full + ".md5"
        try:
            with open(md5_path, encoding="ascii", errors="replace") as f:
                old = (f.read().split() or [""])[0]
        except (OSError, IndexError):
            old = ""
        if old.lower() == digest:
            result.append((rel + ".md5", digest, False))
            continue
        with open(md5_path, "w", encoding="ascii", newline="") as f:
            f.write(digest)
        result.append((rel + ".md5", digest, True))
    return result


def find_root():
    """Repository root: the current directory if it holds the repository add-ons, else the nearest parent of this script that does."""
    marker = lambda d: any(os.path.isdir(os.path.join(d, folder)) for _, _, folder in REPOS.values())
    cwd = os.getcwd()
    if marker(cwd):
        return cwd
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        if marker(d):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return cwd
        d = parent


def main():
    ap = argparse.ArgumentParser(description="Generate catalog.json from the addons.xml sources of repo.dexe.")
    ap.add_argument("--root", default=None, help="repository root (default: auto-detected)")
    ap.add_argument("--out", default="catalog.json", help="output file, relative to --root (default: catalog.json)")
    ap.add_argument("--no-remote", action="store_true", help="do not download remote sources")
    ap.add_argument("--pretty", action="store_true", help="indented JSON output")
    ap.add_argument("--no-md5", action="store_true", help="do not update addons.xml.md5 files")
    ap.add_argument("--strict", action="store_true", help="exit with status 1 if any source could not be read")
    args = ap.parse_args()

    root = os.path.abspath(args.root or find_root())
    out_path = os.path.join(root, args.out)
    previous, prev_entries = load_previous(out_path)
    catalog, reports = build(root, allow_remote=not args.no_remote, previous=previous, prev_entries=prev_entries)
    with open(out_path, "w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
        else:
            json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print_report(catalog, reports)
    if not args.no_md5:
        log("addons.xml.md5")
        for rel, digest, changed in update_md5(root):
            log(f"  {'updated  ' if changed else 'unchanged'} {rel}  {digest}")
    total = sum(r["count"] for r in catalog["repos"].values())
    parts = ", ".join("%s: %d" % (k, v["count"]) for k, v in catalog["repos"].items())
    log(f"Done: {out_path} - {total} add-ons ({parts})")
    failed = [r for r in reports[0] if r[4] is None]
    if failed and args.strict:
        log(f"Error: {len(failed)} source(s) could not be read")
        sys.exit(1)


if __name__ == "__main__":
    main()
