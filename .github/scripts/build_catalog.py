#!/usr/bin/env python3
"""
build_catalog.py - generates catalog.json for the add-on catalog on deklica.github.io.

Usage (the repository root is detected automatically, so the script can be run from anywhere):
    python3 .github/scripts/build_catalog.py              # update catalog.json (and addons.xml.md5 in GitHub Actions)
    python3 .github/scripts/build_catalog.py --md5        # also write the addons.xml.md5 files locally
    python3 .github/scripts/build_catalog.py --pretty     # indented JSON
    python3 .github/scripts/build_catalog.py --no-remote  # local sources only
    python3 .github/scripts/build_catalog.py --strict     # exit with status 1 if any source failed
    python3 .github/scripts/build_catalog.py --no-contents            # skip the third-party repository contents
    python3 .github/scripts/build_catalog.py --only repository.umbrella  # check one third-party repository
    python3 .github/scripts/build_catalog.py --out-dir ../deklica.github.io  # write the results into a site copy

Sources are read from the <dir> entries of the repository add-ons listed in REPOS (addon.xml inside
the newest repository zip, or the plain addon.xml next to it). Entries pointing at this repository
are read from the working tree; everything else is downloaded and marked as external.

Third-party repositories (every repository add-on in the catalogs except the own ones): their real
sources are read from addon.xml inside their zip (local folder, else downloaded from their datadir),
each source is fetched and the add-ons are written to catalog/<repository id>.json. The entry in
catalog.json gets a "contents" summary (count, status of the sources) and own add-ons get "newer"
when a third-party repository carries a higher version of the same add-on.

Dates: for local add-ons the date comes from git history (first commit of the current zip), so a
full clone is required - in GitHub Actions use actions/checkout with fetch-depth: 0. For remote
add-ons the date of the current zip is taken from the GitHub API or the Last-Modified header and
remembered in catalog.json; GITHUB_TOKEN / GH_TOKEN is used for the API when present.

Requires Python 3.8+ and the standard library only.
"""

import argparse
import concurrent.futures
import datetime as dt
import email.utils
import gzip
import hashlib
import html
import http.client
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
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
# Some servers serve a repository only to Kodi (any other User-Agent gets a redirect or an error page). Such sources
# are probed once more with a browser's User-Agent, so the site knows that their zips cannot be downloaded from a browser.
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
BROWSER_OK_HOSTS = re.compile(r"^https?://(raw\.githubusercontent\.com|github\.com|[^/]+\.github\.io)/", re.I)   # never gated

# Third-party repository contents
CONTENTS_DIR = "catalog"                                   # catalog/<repository id>.json, relative to the root
CONTENTS_DEAD = "dead"                                     # catalog/dead/: files of repositories removed from the catalogs
CONTENTS_SKIP = {"repository.dexe", "repository.roooar"}   # own catalogs, already on the site
DEPRECATED_FOLDER = "repos/_Deprecated"                    # zips of repositories that are down (not in any catalog)
DEPRECATED_ICONS = "deprecated"                            # catalog/deprecated/<id>.png: icons taken from those zips
DEPRECATED_FILE = "deprecated.json"                        # catalog/deprecated.json: only the site's "Deprecated" chip reads it
DEPRECATED_SEEN = set()                                    # ids of the zips found in DEPRECATED_FOLDER in this run
CONTENTS_WORKERS = 8                                       # parallel downloads
CONTENTS_TIMEOUT = 20                                      # seconds per request
CONTENTS_MAX_ZIP = 12 * 1024 * 1024                        # largest repository zip downloaded from a datadir
CONTENTS_MAX_XML = 40 * 1024 * 1024                        # largest addons.xml accepted
ZIP_FOLDERS = ["repo", "repos", "zips", "misc"]            # local folders that hold repository zips
NEWER_LIMIT = 3                                            # at most N "newer version in ..." hints per add-on
NEWER_MAX_MAJOR_JUMP = 3                                   # ignore "newer" versions like 421.1.0 for 1.0.2 (build repos)
DEVICE_HOST_RE = re.compile(r"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?/", re.I)   # served by an add-on on the device
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
    """Sortable key: each part is compared by its number first, letters after it only break ties
    (1.2.0a > 1.2.0, but 1.5 > 1.2c and 100.0.34 > 100.0.30i)."""
    key = []
    for p in re.split(r"[.\-~+]", v or "0"):
        m = re.match(r"(\d*)(.*)", p)
        num, rest = m.group(1), m.group(2)
        key.append((0, int(num), rest) if num else (1, 0, rest))
    return key


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
            remaining = r.headers.get("X-RateLimit-Remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) < 3:
            _gh_state["limited"] = True        # stop before the limit; the remaining dates fall back to version changes
            log("  warning: GitHub API quota almost used up; remaining dates fall back to version changes"
                + ("" if token else " (set GITHUB_TOKEN for a higher limit)"))
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


SUMMARY_MAX = 200                                          # longer summaries are cut at a word boundary
SUMMARY_LANGS = ("en_gb", "en", "en_us")                   # <summary lang="...">, in this order; else one without lang; other languages: none


def pick_summary(items, name=None):
    """items: [(lang, text)] from <summary> elements -> one short plain-text summary, or None."""
    items = [((lang or "").strip().lower().replace("-", "_"), text) for lang, text in items if text and text.strip()]
    best = next((t for l in SUMMARY_LANGS for lang, t in items if lang == l), None) \
        or next((t for lang, t in items if not lang), None)
    if not best:
        return None
    text = clean_name(html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", best, flags=re.S)))
    if not text or (name and text.lower() == clean_name(name).lower()):
        return None
    if len(text) > SUMMARY_MAX:
        text = text[:SUMMARY_MAX].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"
    return text


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
        zpath = re.search(r"<path>([^<]*)</path>", block)
        reqs = [(m.group(1), 'optional="true"' in m.group(0),
                 (re.search(r'version="([^"]+)"', m.group(0)) or [None, None])[1])
                for m in re.finditer(r'<import\b[^>]*addon="([^"]+)"[^>]*>', block)]
        summ = [((re.search(r'lang="([^"]*)"', m.group(1)) or [None, None])[1], m.group(2))
                for m in re.finditer(r"<summary\b([^>]*)>(.*?)</summary>", block, re.S)]
        return {"id": attr("id"), "name": attr("name"), "version": attr("version"),
                "author": attr("provider-name"), "points": [(p, " ".join(provides)) for p in points],
                "summary": pick_summary(summ, attr("name")),
                "icon": icon.group(1).strip() if icon else "icon.png",
                "platform": plat.group(1).strip() if plat else None, "broken": "<broken" in block,
                "path": zpath.group(1).strip() if zpath else None, "requires": reqs}
    points, icon, platform, broken, zpath = [], None, None, False, None
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
            zp = ext.find("path")                      # Kodi 19+: zip location relative to the datadir (per-platform builds)
            if zp is not None and (zp.text or "").strip():
                zpath = zp.text.strip()
            if ext.find("broken") is not None:
                broken = True
    reqs = [(imp.get("addon"), (imp.get("optional") or "").lower() == "true", imp.get("version"))
            for imp in el.findall("requires/import") if imp.get("addon")]
    summ = [(e.get("lang"), "".join(e.itertext())) for e in el.iter("summary")]
    return {"id": el.get("id"), "name": el.get("name"), "version": el.get("version"),
            "author": el.get("provider-name"), "points": points, "summary": pick_summary(summ, el.get("name")),
            "icon": icon or "icon.png",
            "platform": platform, "broken": broken, "path": zpath, "requires": reqs}


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
def load_previous(path, allow_remote=True):
    """Returns (per add-on summary, full entries per catalog, where it came from) from the previous catalog.json.
    Without a local file (sparse checkout, fresh clone) the published one is taken from GitHub, so that
    dates of external add-ons are not looked up again and nothing is reported as new."""
    data, where = None, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        where = path
    except (OSError, ValueError):
        if allow_remote:
            try:
                data = json.loads(fetch(RAW + "catalog.json"))
                where = RAW + "catalog.json"
            except Exception as e:
                log(f"  warning: no previous catalog ({e})")
    try:
        summary = {(rk, a["id"]): {"version": a.get("version"), "updated": a.get("updated"),
                                   "added": a.get("added"), "has_added": "added" in a}
                   for rk, r in (data or {}).get("repos", {}).items() for a in r.get("addons", [])}
        entries = {rk: list(r.get("addons", [])) for rk, r in (data or {}).get("repos", {}).items()}
        return summary, entries, where
    except (KeyError, TypeError, AttributeError):
        return {}, {}, None


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
                "summary": row.get("summary"),
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
                # repository add-ons keep their datadir: build_contents() needs it to find their zip, also in a run
                # that does not read this source again (--no-remote, source down) and takes the entry from before
                **({"datadir": src["datadir"]} if types[0] == "repository" else {}),
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


# ---------------------------------------------------------------------------
# Contents of the third-party repositories listed in the catalogs
# ---------------------------------------------------------------------------
def repository_dirs(text):
    """<dir> entries of a repository add-on (legacy single-dir layout included): info, checksum, datadir, Kodi range."""
    ext = re.search(r'<extension\b[^>]*point="xbmc\.addon\.repository"[^>]*>(.*?)</extension>', text, re.S)
    body = ext.group(1) if ext else text
    blocks = [(re.match(r"<dir\b[^>]*>", m.group(0)).group(0), m.group(1))
              for m in re.finditer(r"<dir\b[^>]*>(.*?)</dir>", body, re.S)]
    if not blocks:
        blocks = [("<dir>", body)]
    dirs = []
    for head, b in blocks:
        info = re.search(r"<info\b[^>]*>(.*?)</info>", b, re.S)
        if not info or not info.group(1).strip():
            continue
        url = info.group(1).strip()
        chk = re.search(r"<checksum\b[^>]*>(.*?)</checksum>", b, re.S)
        dd = re.search(r"<datadir\b[^>]*>(.*?)</datadir>", b, re.S)
        datadir = (dd.group(1).strip() if dd and dd.group(1).strip() else url.rsplit("/", 1)[0]).rstrip("/") + "/"
        kmin = re.search(r'minversion="([^"]+)"', head)
        kmax = re.search(r'maxversion="([^"]+)"', head)
        dirs.append({"info": url, "checksum": (chk.group(1).strip() or None) if chk else None, "datadir": datadir,
                     "kodi_min": kmin.group(1) if kmin else None, "kodi_max": kmax.group(1) if kmax else None})
    return dirs


def fetch_status(url, limit=None, timeout=CONTENTS_TIMEOUT, ua=USER_AGENT):
    """GET with timing. Returns (bytes or None, http status, milliseconds, error text)."""
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
        except (TimeoutError, socket.timeout, ConnectionResetError, http.client.RemoteDisconnected):
            time.sleep(2)                                       # one retry: a slow host is not a dead host
            r = urllib.request.urlopen(req, timeout=timeout)
        with r:
            data = r.read(limit + 1) if limit else r.read()
            code = r.status
        ms = int((time.monotonic() - t0) * 1000)
        if limit and len(data) > limit:
            return None, code, ms, "file too large"
        if data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except OSError:
                return None, code, ms, "invalid gzip"
        return data, code, ms, None
    except urllib.error.HTTPError as e:
        return None, e.code, int((time.monotonic() - t0) * 1000), f"HTTP {e.code}"
    except Exception as e:
        msg = str(getattr(e, "reason", e)) or e.__class__.__name__
        return None, None, int((time.monotonic() - t0) * 1000), re.sub(r"\s+", " ", msg)[:100]


def find_repository_zip(root, aid, version):
    """Local zip of a repository add-on: the wanted version, else the newest one. Returns a path relative to root."""
    found = []
    for folder in ZIP_FOLDERS:
        for sub in (os.path.join(folder, aid), folder):
            full = os.path.join(root, sub)
            if not os.path.isdir(full):
                continue
            for fn in os.listdir(full):
                m = re.match(re.escape(aid) + r"-(.+)\.zip$", fn)
                if m:
                    found.append((m.group(1) == version, version_key(m.group(1)), f"{sub}/{fn}"))
    if not found:
        return None, False
    found.sort(reverse=True)
    return found[0][2], found[0][0]


def addon_xml_from_zip(data_or_path, aid):
    try:
        with zipfile.ZipFile(data_or_path) as z:
            name = next((n for n in z.namelist() if n.lower() == f"{aid}/addon.xml".lower()), None)
            if not name:
                name = next((n for n in z.namelist() if n.lower().endswith("/addon.xml") and n.count("/") == 1), None)
            if name:
                return z.read(name).decode("utf-8", "replace"), None
            return None, "addon.xml not in zip"
    except (zipfile.BadZipFile, OSError) as e:
        return None, f"bad zip: {e}"


def is_newer(candidate, ours):
    """Kodi-style comparison, ignoring build suffixes of the same base (1.0~omega vs 1.0~nexus) and the inflated
    versions that build repositories use (421.1.0 for 1.0.2)."""
    base = lambda v: re.split(r"[~+]", v or "0", maxsplit=1)[0]
    if version_key(base(candidate)) <= version_key(base(ours)):
        return False
    major = lambda v: (_major_minor(v)[0] or 0)
    return major(candidate) <= major(ours) + NEWER_MAX_MAJOR_JUMP


def contents_kodi(dir_):
    lo, hi = kodi_from_dir(dir_.get("kodi_min"), dir_.get("kodi_max"))
    return None if lo is None and hi is None else {"min": lo, "max": hi}


def dir_is_current(dir_):
    """A <dir> that a current Kodi (19+) would use; a broken source only for old versions does not break the repo today."""
    _, hi = kodi_from_dir(dir_.get("kodi_min"), dir_.get("kodi_max"))
    return hi is None or hi >= 19


def contents_entries(text, dir_, dir_index):
    rows = []
    for block in ADDON_BLOCK_RE.findall(COMMENT_RE.sub("", text)):
        a = parse_block(block)
        if a.get("id"):
            rows.append(a)
    out = []
    for r in rows:
        aid = r["id"]
        types = kodi_types(r["points"], aid)
        if aid in TYPE_OVERRIDES:
            types = [TYPE_OVERRIDES[aid]] + [t for t in types if t != TYPE_OVERRIDES[aid]]
        lo, hi = kodi_range([kodi_from_addon(aid, r["version"], r.get("requires", [])),
                             kodi_from_dir(dir_.get("kodi_min"), dir_.get("kodi_max"))])
        platforms = [p for p in (r["platform"] or "").split() if p != "all"]
        out.append({
            "id": aid,
            "name": clean_name(r["name"]) or aid,
            "version": r["version"] or "0",
            "author": clean_name(r["author"]) or None,
            "summary": r.get("summary"),
            "type": types[0],
            "types": types,
            "dependency": types[0] in DEPENDENCY_TYPES,
            "platforms": platforms,
            "broken": r["broken"],
            "icon": (dir_["datadir"] + aid + "/" + r["icon"]) if r["icon"] else None,
            "kodi": None if lo is None and hi is None else {"min": lo, "max": hi},
            "src": dir_index,
            "zip": dir_["datadir"] + (r.get("path").lstrip("/") if r.get("path") else f"{aid}/{aid}-{r['version'] or '0'}.zip"),   # as Kodi fetches it
            "_requires": sorted({d for d, opt, _ in r.get("requires", []) if not opt}),
        })
    return out


def merge_contents(entries):
    """One entry per id and Kodi range: the same version in several dirs is one entry, a lower version whose
    Kodi range overlaps a higher one is dropped, versions for different Kodi releases stay separate."""
    by_id = {}
    for e in entries:
        by_id.setdefault(e["id"], []).append(e)
    out = []
    for aid, items in by_id.items():
        items.sort(key=lambda e: version_key(e["version"]), reverse=True)
        kept = []
        for e in items:
            rng = (e["kodi"]["min"], e["kodi"]["max"]) if e["kodi"] else (None, None)
            for k in kept:
                krng = (k["kodi"]["min"], k["kodi"]["max"]) if k["kodi"] else (None, None)
                if k["version"] == e["version"] and set(k.get("platforms") or []) != set(e.get("platforms") or []):
                    continue                           # same version built per platform (own zip each): separate entries
                if k["version"] == e["version"]:
                    u = range_union(krng, rng)
                    k["kodi"] = None if u == (None, None) else {"min": u[0], "max": u[1]}
                    if not k["icon"]:
                        k["icon"] = e["icon"]
                    k["_requires"] = sorted(set(k.get("_requires", [])) | set(e.get("_requires", [])))
                    break
                if ranges_overlap(krng, rng):
                    break                                  # superseded by the higher version
            else:
                kept.append(dict(e))
        out.extend(kept)
    # a module/helper required by exactly one add-on of the repository is shown as its part (same rule as own catalogs)
    ids = {e["id"] for e in out}
    types_by_id = {e["id"]: e["type"] for e in out}
    importers = {}
    carried = set()                            # entries kept from the previous file: their parent is kept as it was
    for e in out:
        if "_requires" not in e:
            carried.add(e["id"])
        for dep in e.pop("_requires", []):
            if dep in ids and dep != e["id"]:
                importers.setdefault(dep, set()).add(e["id"])
    for e in out:
        if e["id"] in carried:
            e["parent"] = e.get("parent") if e.get("parent") in ids else None
            e["dependency"] = e["type"] in DEPENDENCY_TYPES or bool(e["parent"])
            continue
        users = importers.get(e["id"], set())
        parent = None
        helper = e["id"].startswith("script.module.") or (e["id"].startswith("script.") and ".helper" in e["id"])
        if len(users) == 1 and helper and e["type"] not in ("video", "audio", "image", "skin", "repository"):
            user = next(iter(users))
            if types_by_id.get(user) not in DEPENDENCY_TYPES:
                parent = user
        e["parent"] = parent
        e["dependency"] = e["type"] in DEPENDENCY_TYPES or bool(parent)
    out.sort(key=lambda e: e["name"].lower())
    children = {}
    for e in out:
        if e["parent"]:
            children.setdefault(e["parent"], []).append(e["id"])
    for e in out:
        e["children"] = sorted(set(children.get(e["id"], [])))
    return out


def load_contents_file(path, allow_remote=False):
    """Previous catalog/<id>.json: local file, else (when allowed) the published one from GitHub."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        if not allow_remote:
            return None
        try:
            data = json.loads(fetch(RAW + CONTENTS_DIR + "/" + os.path.basename(path)))
        except Exception:
            return None
    return data if isinstance(data, dict) and "addons" in data else None


def contents_comparable(doc):
    d = dict(doc)
    d.pop("generated", None)
    d["sources"] = [{k: v for k, v in s.items() if k not in ("ms", "http")} for s in doc.get("sources", [])]
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Repositories that are down: zips kept in repos/_Deprecated
# ---------------------------------------------------------------------------
def deprecated_jobs(root, out_dir):
    """Repositories that are down: one job per zip in DEPRECATED_FOLDER, read from the addon.xml inside the zip.
    They are described like the other third-party repositories (catalog/<id>.json, sources checked on every run),
    but stay out of catalog/index.json and the "newer version" hints; catalog/deprecated.json lists them for the
    site's "Deprecated" chip."""
    folder = os.path.join(root, DEPRECATED_FOLDER)
    jobs = {}
    if not os.path.isdir(folder):
        return jobs
    icon_dir = os.path.join(out_dir, DEPRECATED_ICONS)
    for fn in sorted(os.listdir(folder), key=str.lower):
        if not fn.lower().endswith(".zip"):
            continue
        path = os.path.join(folder, fn)
        text, err = addon_xml_from_zip(path, fn[:-4].rsplit("-", 1)[0])
        block = ADDON_BLOCK_RE.search(text or "")
        a = parse_block(block.group(0)) if block else {}
        aid = a.get("id")
        if not aid:
            log(f"Deprecated: {fn}: {err or 'no add-on id in addon.xml'}")
            continue
        if aid in jobs and version_key(jobs[aid]["version"]) >= version_key(a.get("version") or "0"):
            continue
        icon_url = None
        try:                                            # the icon from the zip, so the site can show it
            with zipfile.ZipFile(path) as z:
                want = "/" + a["icon"].lstrip("/").lower()
                src = next((n for n in z.namelist() if n.lower().endswith(want) and n.count("/") == want.count("/")), None)
                if src and z.getinfo(src).file_size <= 1024 * 1024:
                    data = z.read(src)
                    ext = os.path.splitext(src)[1].lower() or ".png"
                    dest = os.path.join(icon_dir, aid + ext)
                    old = None
                    if os.path.exists(dest):
                        with open(dest, "rb") as f:
                            old = f.read()
                    if old != data:
                        os.makedirs(icon_dir, exist_ok=True)
                        with open(dest, "wb") as f:
                            f.write(data)
                    icon_url = RAW + f"{CONTENTS_DIR}/{DEPRECATED_ICONS}/{aid}{ext}"
        except (zipfile.BadZipFile, OSError, KeyError):
            pass
        jobs[aid] = {"id": aid, "name": clean_name(a.get("name")) or aid, "version": a.get("version") or "0",
                     "datadir": None, "icon": icon_url, "author": clean_name(a.get("author")) or None,
                     "summary": a.get("summary"), "deprecated": True, "zip_rel": f"{DEPRECATED_FOLDER}/{fn}"}
    return jobs


def write_deprecated(out_dir, jobs, run_time):
    """catalog/deprecated.json from the deprecated jobs; "online" = the same rule as the status of any other repository:
    every source for current Kodi releases works and serves add-ons (one dead source of its own = still down, even
    when shared dependency sources such as scrapers or modules are up)."""
    path_out = os.path.join(out_dir, DEPRECATED_FILE)
    prev = {}
    try:
        with open(path_out, encoding="utf-8") as f:
            prev = {a["id"]: a for a in json.load(f).get("addons", [])}
    except (OSError, ValueError):
        pass
    items = []
    for j in jobs.values():
        if not j.get("deprecated"):
            continue
        doc = j["doc"]
        srcs = doc["sources"]
        online = doc["status"] in ("ok", "warn") and doc["count"] > 0
        p = (prev.get(j["id"]) or {}).get("contents") or {}
        last_ok = run_time if online and j.get("checked_now") else p.get("last_ok")
        contents = {"count": doc["count"], "status": doc["status"], "sources": len(srcs),
                    "failed": sum(1 for s in srcs if s["status"] == "error"), "checked": run_time,
                    "file": f"{CONTENTS_DIR}/{j['id']}.json"}
        if last_ok:
            contents["last_ok"] = last_ok
        if doc.get("error"):
            contents["error"] = doc["error"]
        j["online"] = online
        items.append({"id": j["id"], "name": j["name"], "version": j["version"], "author": j.get("author"),
                      "summary": j.get("summary"), "type": "repository", "dependency": False, "platforms": [],
                      "broken": False, "icon": j.get("icon"), "kodi": None, "zip": j["zip_rel"],
                      "online": online, "contents": contents})
    ids = {i["id"] for i in items}
    items += [a for aid, a in prev.items() if aid not in ids and aid in DEPRECATED_SEEN]   # not described in this run
    items.sort(key=lambda x: x["name"].lower())
    with open(path_out, "w", encoding="utf-8") as f:
        json.dump({"generated": run_time, "addons": items}, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    back = [i for i in items if i.get("online")]
    log(f"Deprecated: {len(items)} repositories in {DEPRECATED_FOLDER}, online: {len(back)}")
    for i in back:
        j = jobs.get(i["id"]) or {}
        ok = [s["info"] for s in j.get("doc", {}).get("sources", []) if s["status"] == "ok"]
        log(f"  ONLINE  {i['id']} {i['version']} ({(i.get('contents') or {}).get('count', '?')} add-ons)" + (": " + ", ".join(ok) if ok else ""))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and back:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {DEPRECATED_FOLDER}: online\n\n")
            for i in back:
                f.write(f"- ONLINE **{i['id']}** {i['version']}\n")
            f.write("\n")


def build_contents(catalog, root, allow_remote, only=None, out_root=None, prev_entries=None, fill_missing=False):
    """Reads every third-party repository listed in the catalogs and writes catalog/<id>.json for each.
    Adds "contents" to the repository entries and "newer" to the other add-ons. Returns the report rows."""
    run_time = now_iso()
    out_dir = os.path.join(out_root or root, CONTENTS_DIR)
    os.makedirs(out_dir, exist_ok=True)

    # repository add-ons across the catalogs, one job per id (highest version wins)
    jobs = {}
    for rk, repo in catalog["repos"].items():
        for a in repo["addons"]:
            if a["type"] != "repository" or a["id"] in CONTENTS_SKIP:
                continue
            if only and a["id"] not in only:
                continue
            j = jobs.get(a["id"])
            if j is None or version_key(a["version"]) > version_key(j["version"]):
                jobs[a["id"]] = {"id": a["id"], "name": a["name"], "version": a["version"],
                                 "datadir": a.get("datadir"), "icon": a.get("icon")}

    # repositories that are down (zips in repos/_Deprecated): described like the others, listed only in deprecated.json
    dep = deprecated_jobs(root, out_dir)
    DEPRECATED_SEEN.clear(); DEPRECATED_SEEN.update(dep)
    for aid, j in dep.items():
        if aid not in jobs and aid not in CONTENTS_SKIP and (not only or aid in only):
            jobs[aid] = j

    # a repository removed from the catalogs: its file moves to catalog/dead/ (index.json is rebuilt below anyway);
    # if the repository comes back, that copy is its previous state again (dates, last_ok)
    dead_dir = os.path.join(out_dir, CONTENTS_DEAD)
    if not only:
        listed = {a["id"] for r in catalog["repos"].values() for a in r["addons"] if a["type"] == "repository"} | set(dep)
        for fn in os.listdir(out_dir):
            stem = fn[:-5] if fn.endswith(".json") else None
            if stem and stem not in ("index", DEPRECATED_FILE[:-5]) and stem not in listed:
                os.makedirs(dead_dir, exist_ok=True)
                os.replace(os.path.join(out_dir, fn), os.path.join(dead_dir, fn))
                log(f"Moved {CONTENTS_DIR}/{fn} to {CONTENTS_DIR}/{CONTENTS_DEAD}/: repository no longer in the catalogs")

    report = []
    if not jobs:
        return report

    # 1. addon.xml of each repository, in this order: local zip of the catalog version, previous file of the same
    #    version, zip downloaded from the datadir, any local zip (older version), previous file
    def read_dirs(j):
        prev = load_contents_file(os.path.join(out_dir, j["id"] + ".json"), allow_remote)
        if prev is None:                                            # repository that was removed and is back
            prev = load_contents_file(os.path.join(dead_dir, j["id"] + ".json"), False)
        j["prev"] = prev
        # a repository never described before is read from the network even in a --no-remote run (push), once
        j["remote"] = allow_remote or (fill_missing and prev is None)
        if j.get("zip_rel"):                                    # repos/_Deprecated: its own zip is the only source
            text, err = addon_xml_from_zip(os.path.join(root, j["zip_rel"]), j["id"])
            j["dirs"], j["zip"] = (repository_dirs(text), j["zip_rel"]) if text else (None, j["zip_rel"])
            if not text:
                j["zip_error"] = err
            return
        rel, exact = find_repository_zip(root, j["id"], j["version"])
        local = None
        if rel:
            text, err = addon_xml_from_zip(os.path.join(root, rel), j["id"])
            if text:
                local = (repository_dirs(text), rel)
            else:
                j["zip_error"] = err
        if local and exact:
            j["dirs"], j["zip"] = local
            return
        if prev and prev.get("version") == j["version"] and prev.get("dirs"):
            j["dirs"], j["zip"] = prev["dirs"], prev.get("zip")
            return
        url = f"{j['datadir']}{j['id']}/{j['id']}-{j['version']}.zip" if j["datadir"] else None
        if not url and prev and prev.get("version") == j["version"]:
            url = prev.get("zip")                               # entry taken from before: its zip URL is in the file
        if j["remote"] and url:
            data, code, ms, err = fetch_status(url, CONTENTS_MAX_ZIP)
            if data is not None:
                text, err = addon_xml_from_zip(io.BytesIO(data), j["id"])
                if text:
                    j["dirs"], j["zip"] = repository_dirs(text), url
                    return
            j["zip_error"] = f"{err}: {url}"
        if local:
            j["dirs"], j["zip"] = local
            return
        j["dirs"] = prev.get("dirs") if prev else None
        j["zip"] = prev.get("zip") if prev else None
        if not j.get("zip_error"):
            j["zip_error"] = "skipped (--no-remote)" if not j["remote"] else "no local zip and no datadir"

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONTENTS_WORKERS) as pool:
        list(pool.map(read_dirs, jobs.values()))
    for rid in [k for k, j in jobs.items() if not j.get("prev") and not j["remote"]]:   # without network a repository
        del jobs[rid]                                                                    # not seen before cannot be described yet
    if not jobs:
        return report

    # 2. every distinct source URL once (info files parsed, checksum files only checked); a --no-remote run reads
    #    only the sources of repositories it has to describe anew, the others keep their previous result
    urls = {}
    for j in jobs.values():
        if not j["remote"]:
            continue
        for d in j.get("dirs") or []:
            if DEVICE_HOST_RE.match(d["info"]):
                continue
            urls.setdefault(d["info"], "info")
            if d.get("checksum"):
                urls.setdefault(d["checksum"], "checksum")
    results = {}
    if urls:
        def grab(item):
            url, kind = item
            data, code, ms, err = fetch_status(url, CONTENTS_MAX_XML if kind == "info" else 64 * 1024)
            text = None
            if data is not None and kind == "info":
                text = data.decode("utf-8", "replace")
                if "<addon" not in text:
                    err, data = "not an addons.xml", None
            results[url] = {"http": code, "ms": ms, "error": err, "text": text, "ok": data is not None}
            if kind == "info" and data is not None and not BROWSER_OK_HOSTS.match(url):
                # the same file as a browser would ask for it: a redirect/error page means the server serves Kodi only
                bdata = fetch_status(url, CONTENTS_MAX_XML, ua=BROWSER_UA)[0]
                results[url]["browser"] = bdata is not None and b"<addon" in bdata
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONTENTS_WORKERS) as pool:
            list(pool.map(grab, urls.items()))

    # 3. per repository: entries, status, file
    by_addon = {}                                   # id -> [(repo id, repo name, version, kodi range)]
    for j in jobs.values():
        prev = j.get("prev")
        dirs = j.get("dirs")
        doc = {"id": j["id"], "name": j["name"], "version": j["version"], "generated": run_time,
               "zip": j.get("zip"), "dirs": dirs or [], "status": "ok", "sources": [], "count": 0, "addons": []}
        if not dirs:
            doc["status"] = "error"
            doc["error"] = j.get("zip_error") or "no sources in addon.xml"
            if prev:
                doc["addons"], doc["count"] = prev.get("addons", []), prev.get("count", 0)
                doc["sources"], doc["kept"] = prev.get("sources", []), True
        else:
            entries = []
            carried_ids = set()
            prev_by_url = {}
            if prev:                                    # previous entries per source URL (a URL may serve several dirs)
                for i, s in enumerate(prev.get("sources", [])):
                    prev_by_url.setdefault(s.get("info"), []).extend(a for a in prev.get("addons", []) if a.get("src") == i)
            broken_now = False
            j["checked_now"] = any(results.get(d["info"]) is not None for d in dirs)   # False in --no-remote runs
            for i, d in enumerate(dirs):
                s = {"info": d["info"], "checksum": d.get("checksum"), "datadir": d["datadir"],
                     "kodi": contents_kodi(d), "status": "ok", "http": None, "ms": None, "count": 0, "error": None}
                r = results.get(d["info"])
                if DEVICE_HOST_RE.match(d["info"]):
                    s["status"], s["error"] = "device", "served by the add-on itself on the device, cannot be checked"
                elif r is None:                         # --no-remote: previous result of this source, if any
                    kept = prev_by_url.pop(d["info"], None)
                    ps = next((x for x in (prev or {}).get("sources", []) if x.get("info") == d["info"]), None)
                    if ps:
                        s.update({k: ps.get(k) for k in ("status", "http", "ms", "error", "checksum_error", "count", "kept", "browser") if k in ps})
                    else:
                        s["status"], s["error"] = "skipped", "not checked"
                    for a in kept or []:
                        a = dict(a); a["src"] = i; entries.append(a); carried_ids.add(a["id"])
                    if not ps:
                        s["count"] = len(kept or [])
                else:
                    s["http"], s["ms"] = r["http"], r["ms"]
                    if r["ok"]:
                        got = contents_entries(r["text"], d, i)
                        entries.extend(got)
                        s["count"] = len(got)
                        if r.get("browser") is False:
                            s["browser"] = False        # served to Kodi only: zips cannot be downloaded from a browser
                    else:
                        s["status"], s["error"] = "error", r["error"]
                        kept = prev_by_url.pop(d["info"], None)
                        if kept:
                            for a in kept:
                                a = dict(a); a["src"] = i; entries.append(a); carried_ids.add(a["id"])
                            s["count"], s["kept"] = len(kept), True
                    if d.get("checksum"):
                        c = results.get(d["checksum"])
                        if c and not c["ok"]:
                            s["checksum_error"] = c["error"]
                            if s["status"] == "ok":
                                s["status"] = "error"
                                s["error"] = f"checksum: {c['error']}"
                if s["status"] == "error" and dir_is_current(d):
                    broken_now = True
                doc["sources"].append(s)
            doc["addons"] = merge_contents(entries)
            # Dates: third-party repositories give none, so they are tracked from run to run - a version first seen
            # today is dated today ("updated"), an id first seen today is also "added" today. Entries present at the
            # first run of a repository stay undated.
            if prev:
                prev_dates = {}
                prev_ids = set()
                for x in prev.get("addons", []):
                    prev_ids.add(x["id"])
                    prev_dates[f"{x['id']}@{x['version']}"] = (x.get("updated"), x.get("added"))
                for e in doc["addons"]:
                    if "updated" in e and e["id"] in carried_ids:
                        continue
                    key = f"{e['id']}@{e['version']}"
                    if key in prev_dates:
                        e["updated"], e["added"] = prev_dates[key]
                    elif e["id"] in prev_ids:
                        e["updated"] = run_time
                        e["added"] = next((d for u, d in (prev_dates[k] for k in prev_dates if k.startswith(e["id"] + "@")) if d), None)
                    else:
                        e["updated"] = e["added"] = run_time
            doc["addons"].sort(key=lambda e: e["name"].lower())
            doc["addons"].sort(key=lambda e: e.get("updated") or "", reverse=True)
            doc["count"] = len(doc["addons"])
            failed = [s for s in doc["sources"] if s["status"] == "error"]
            skipped = [s for s in doc["sources"] if s["status"] == "skipped"]
            if all(s["status"] == "device" for s in doc["sources"]):
                doc["status"] = "device"
            elif skipped and len(skipped) + sum(1 for s in doc["sources"] if s["status"] == "device") == len(doc["sources"]):
                doc["status"] = prev.get("status", "unknown") if prev else "unknown"
            elif broken_now:
                doc["status"] = "error"
            elif failed:
                doc["status"] = "warn"                  # only sources for old Kodi versions fail
        # write only when something other than the timestamps changed
        path = os.path.join(out_dir, j["id"] + ".json")
        changed = prev is None or not os.path.exists(path) or contents_comparable(prev) != contents_comparable(doc)
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
                f.write("\n")
            dead = os.path.join(dead_dir, j["id"] + ".json")
            if os.path.exists(dead):                        # the repository is back: its old copy is no longer needed
                os.remove(dead)
        j["doc"] = doc
        if j.get("deprecated"):                         # no "newer version" hints from them, own lines in the log
            continue
        for a in doc["addons"]:
            by_addon.setdefault(a["id"], []).append((j["id"], j["name"], a["version"], a.get("kodi")))
        report.append((j["id"], doc["status"], doc["count"], len(doc["sources"]),
                       [(s["info"], s["error"]) for s in doc["sources"] if s["status"] == "error"],
                       doc.get("error"), changed, j))

    # 3b. catalog/index.json: every add-on of every third-party repository in one compact list (site-wide search)
    index = {"generated": run_time, "addons": []}
    for j in sorted(jobs.values(), key=lambda x: x["id"].lower()):
        if j.get("deprecated"):
            continue
        for a in j["doc"]["addons"]:
            index["addons"].append({**{k: a.get(k) for k in ("id", "name", "version", "author", "type", "dependency", "platforms",
                                                             "broken", "icon", "kodi", "updated", "added")},
                                    **({"summary": a["summary"]} if a.get("summary") else {}),   # only when there is one: smaller file
                                    "repo": j["id"], "rname": j["name"]})
    idx_path = os.path.join(out_dir, "index.json")
    prev_idx = None
    try:
        with open(idx_path, encoding="utf-8") as f:
            prev_idx = json.load(f)
    except (OSError, ValueError):
        pass
    strip = lambda d: json.dumps({k: v for k, v in (d or {}).items() if k != "generated"}, sort_keys=True, ensure_ascii=False)
    if prev_idx is None or strip(prev_idx) != strip(index):
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
    catalog["index_count"] = len(index["addons"])          # the site reserves room for the counts of the "all repos" view
    log(f"Index: {len(index['addons'])} add-ons from {sum(1 for j in jobs.values() if not j.get('deprecated'))} repositories -> {CONTENTS_DIR}/index.json")
    write_deprecated(out_dir, jobs, run_time)

    # 4. summaries into catalog.json
    own_versions = {}                               # (catalog, id) -> versions we carry for any Kodi release
    for rk, repo in catalog["repos"].items():
        for a in repo["addons"]:
            own_versions.setdefault((rk, a["id"]), []).append(a["version"] or "0")
    prev_summary = {(rk, e["id"]): e.get("contents") or {} for rk, es in (prev_entries or {}).items() for e in es}
    for rk, repo in catalog["repos"].items():
        for a in repo["addons"]:
            a.pop("contents", None); a.pop("newer", None)       # stale values of carried-over entries
            j = jobs.get(a["id"]) if a["type"] == "repository" else None
            if j:
                doc = j["doc"]
                failed = [s for s in doc["sources"] if s["status"] == "error"]
                a["contents"] = {"count": doc["count"], "status": doc["status"], "sources": len(doc["sources"]),
                                 "failed": len(failed), "checked": run_time,
                                 "file": f"{CONTENTS_DIR}/{j['id']}.json"}
                # When the repository worked for the last time (on current Kodi releases): set by a real check,
                # carried over from the previous catalog otherwise - so a broken repo shows how long it has been down.
                if doc["status"] in ("ok", "warn") and j.get("checked_now"):
                    last_ok = run_time
                else:
                    last_ok = prev_summary.get((rk, a["id"]), {}).get("last_ok")
                if last_ok:
                    a["contents"]["last_ok"] = last_ok
                j["last_ok"] = last_ok
                if doc.get("error"):
                    a["contents"]["error"] = doc["error"]
            elif a["type"] != "repository":
                best = {}
                own_rng = ((a.get("kodi") or {}).get("min"), (a.get("kodi") or {}).get("max"))
                for rid, rname, ver, kodi in by_addon.get(a["id"], []):
                    # Counts only when the Kodi releases overlap (a skin's 2.1 for Kodi 20 is not an update of 1.4 for
                    # Kodi 19) and when we do not already carry that version for another Kodi release (Orion 5.1.7 for
                    # Kodi 19+ is not an update of our 4.4.1 kept for Kodi 18, whatever Orion's own metadata claims).
                    if not is_newer(ver, a["version"]):
                        continue
                    if not ranges_overlap(own_rng, ((kodi or {}).get("min"), (kodi or {}).get("max"))):
                        continue
                    if any(version_key(v) >= version_key(ver) for v in own_versions.get((rk, a["id"]), [])):
                        continue
                    if rid not in best or version_key(ver) > version_key(best[rid]["version"]):
                        best[rid] = {"repo": rid, "name": rname, "version": ver}
                newer = sorted(best.values(), key=lambda x: version_key(x["version"]), reverse=True)[:NEWER_LIMIT]
                if newer:
                    a["newer"] = newer
    return report


def print_contents_report(report):
    if not report:
        return
    log("Third-party repositories")
    log("=" * 78)
    ok = sum(1 for r in report if r[1] == "ok")
    for rid, status, count, nsrc, failed, error, changed, j in sorted(report, key=lambda r: r[0]):
        mark = {"ok": " ", "warn": "~", "error": "!"}.get(status, "?")
        log(f"  {mark} {rid:<36} {count:>4} add-ons  {nsrc} source(s)  {status}{'  (updated)' if changed else ''}")
        if error:
            log(f"        {error}")
        for url, err in failed:
            log(f"        ERROR {err}: {url}")
        for s in j.get("doc", {}).get("sources", []):
            if s.get("browser") is False:
                log(f"        KODI ONLY (a browser gets no file from it): {s['info']}")
        if status == "error":
            log(f"        last worked: {(j.get('last_ok') or 'never (since tracking began)')[:10]}")
    log(f"  -> {len(report)} repositories, {ok} ok, {sum(1 for r in report if r[1] == 'warn')} with old sources failing, "
        f"{sum(1 for r in report if r[1] == 'error')} broken")
    log("-" * 78)


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
    ap.add_argument("--out", default="catalog.json", help="output file, relative to --out-dir (default: catalog.json)")
    ap.add_argument("--out-dir", default=None, metavar="DIR",
                    help="where catalog.json and the catalog/ folder are written (default: the repository root); e.g. a local copy of the website for testing")
    ap.add_argument("--no-remote", action="store_true", help="do not download remote sources")
    ap.add_argument("--pretty", action="store_true", help="indented JSON output")
    ap.add_argument("--md5", action="store_true",
                    help="also update the addons.xml.md5 files (default only in GitHub Actions; local clones leave them to the Action)")
    ap.add_argument("--strict", action="store_true", help="exit with status 1 if any source could not be read")
    ap.add_argument("--no-contents", action="store_true", help="do not read the third-party repositories")
    ap.add_argument("--only", action="append", metavar="ID", help="read only this third-party repository (repeatable)")
    args = ap.parse_args()

    root = os.path.abspath(args.root or find_root())
    out_root = os.path.abspath(args.out_dir) if args.out_dir else root
    out_path = os.path.join(out_root, args.out)
    previous, prev_entries, prev_where = load_previous(out_path, allow_remote=not args.no_remote)
    log(f"Previous catalog: {prev_where or 'none'}")
    catalog, reports = build(root, allow_remote=not args.no_remote, previous=previous, prev_entries=prev_entries)
    contents_report = []
    if args.no_contents:                 # keep the repository contents and "newer" hints from the previous catalog
        prev_extra = {(rk, e["id"]): e for rk, es in prev_entries.items() for e in es}
        for rk, r in catalog["repos"].items():
            for a in r["addons"]:
                p = prev_extra.get((rk, a["id"]))
                for k in ("contents", "newer"):
                    if p and k in p:
                        a[k] = p[k]
                    else:
                        a.pop(k, None)
    else:
        contents_report = build_contents(catalog, root, allow_remote=not args.no_remote, only=set(args.only or []) or None,
                                         out_root=out_root, prev_entries=prev_entries, fill_missing=args.no_remote)
    with open(out_path, "w", encoding="utf-8") as f:
        if args.pretty:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
        else:
            json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print_report(catalog, reports)
    print_contents_report(contents_report)
    if args.md5 or os.environ.get("GITHUB_ACTIONS") == "true":
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
    