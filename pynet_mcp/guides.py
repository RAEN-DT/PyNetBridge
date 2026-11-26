"""PyNET guides: the knowledge base the PyNET Library installs, read for the AI.

The guides are not part of this package. The PyNET Library installer packs them into a single file,
kb.dat (a zip of Markdown files), in a hidden folder of the user's profile; these functions read it in
place, without extracting anything to disk.
"""
import os
import re
import threading
import zipfile
from pathlib import Path

# Same folder the PyNET Library installer writes to (its AppId, without braces).
_DEFAULT_KB = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) \
    / "RAEN" / "PyNET" / "8E15B020-7FD8-4A1A-A1E8-A5E9E4F6C7F2" / "kb.dat"

NOT_INSTALLED = ("The PyNET guides are not installed on this computer. "
                 "Install PyNET Library (or update it) and try again.")

_lock = threading.Lock()
_cache = {"key": None, "guides": {}}


def kb_path() -> Path:
    """kb.dat's location; PYNET_KB_PATH overrides it (tests, other installs)."""
    override = os.environ.get("PYNET_KB_PATH")
    return Path(override) if override else _DEFAULT_KB


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return fallback


def _load() -> dict:
    """{name: (title, text)} for every .md in kb.dat, reread only when the file changes."""
    path = kb_path()
    try:
        stat = path.stat()
    except OSError:
        return {}
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cache["key"] == key:
            return _cache["guides"]
        guides = {}
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                entry = info.filename.replace("\\", "/")
                if info.is_dir() or not entry.lower().endswith(".md"):
                    continue
                name = entry[:-3]
                text = archive.read(info).decode("utf-8-sig", errors="replace")
                guides[name] = (_title(text, name.rsplit("/", 1)[-1]), text)
        _cache["key"], _cache["guides"] = key, guides
        return guides


def list_guides(contains: str = "") -> list:
    """Every guide as {name, title}, optionally only those whose name or title contains `contains`."""
    needle = contains.strip().lower()
    return [{"name": name, "title": title}
            for name, (title, _) in sorted(_load().items())
            if not needle or needle in name.lower() or needle in title.lower()]


def read_guide(name: str):
    """(text, None) for the guide `name`; (None, reason) when it is not found.

    `name` is a name from list_guides ("docs/pythonnet"); the last part alone ("pythonnet") or a
    trailing ".md" are accepted when they identify a single guide."""
    guides = _load()
    if not guides:
        return None, NOT_INSTALLED
    wanted = name.strip().replace("\\", "/").removesuffix(".md").strip("/")
    if wanted in guides:
        return guides[wanted][1], None
    by_last = [g for g in guides if g.rsplit("/", 1)[-1].lower() == wanted.lower()]
    if len(by_last) == 1:
        return guides[by_last[0]][1], None
    similar = [g for g in guides if wanted.lower() in g.lower()][:10]
    if len(by_last) > 1:
        return None, f"'{name}' matches several guides: {', '.join(by_last)}."
    hint = f" Similar: {', '.join(similar)}." if similar else " Use list_guides to see them all."
    return None, f"No guide named '{name}'.{hint}"
