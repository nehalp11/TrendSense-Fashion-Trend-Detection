"""
Google Drive integration for TrendSense.
Supports:
1. Downloading and syncing SQLite databases directly from Google Drive public/shared links or File IDs.
2. Auto-discovering Google Drive desktop paths (e.g. G:\\My Drive\\... and %USERPROFILE%\\Google Drive)
   and browser downloads from Google Drive.
3. Persisting the connected Google Drive source link/path.
"""
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import requests

CONFIG_FILE = "gdrive_config.json"


def extract_file_id(url_or_id):
    """Extract Google Drive file ID from URL or return raw ID."""
    if not url_or_id:
        return None
    s = str(url_or_id).strip()
    # Match /file/d/<id>
    m = re.search(r"/d/([a-zA-Z0-9_-]{20,})", s)
    if m:
        return m.group(1)
    # Match id=<id>
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", s)
    if m:
        return m.group(1)
    # Match direct ID string (typically 25-45 characters alphanumeric + '-' or '_')
    if re.match(r"^[a-zA-Z0-9_-]{20,60}$", s):
        return s
    return None


def download_gdrive_file(url_or_id, dest_path):
    """
    Download a file from Google Drive (handling confirmation token for large files).
    Returns (success: bool, message: str, file_size: int).
    """
    file_id = extract_file_id(url_or_id)
    if not file_id:
        return False, "Invalid Google Drive link or File ID. Please check the URL.", 0

    dest = Path(dest_path)
    tmp_path = dest.parent / f"{dest.name}.tmp"

    try:
        session = requests.Session()
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        res = session.get(download_url, headers=headers, stream=True, timeout=15)

        # Check for Google Drive virus scan warning / confirmation token for large files
        confirm_token = None
        for k, v in session.cookies.items():
            if k.startswith("download_warning"):
                confirm_token = v
                break

        if not confirm_token and "confirm=" in res.text:
            m = re.search(r"confirm=([0-9A-Za-z_-]+)", res.text)
            if m:
                confirm_token = m.group(1)

        if confirm_token:
            download_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
            res = session.get(download_url, headers=headers, stream=True, timeout=30)

        if res.status_code != 200:
            return False, f"Download failed with HTTP status {res.status_code}. Ensure the file sharing is set to 'Anyone with the link'.", 0

        # Stream download into temporary file
        total_bytes = 0
        with open(tmp_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total_bytes += len(chunk)

        # Validate that the downloaded file is a valid SQLite database
        try:
            con = sqlite3.connect(str(tmp_path))
            cur = con.cursor()
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            con.close()
            if not tables:
                tmp_path.unlink(missing_ok=True)
                return False, "Downloaded file is an empty database or corrupted file.", 0
        except sqlite3.DatabaseError:
            # Maybe the file was an HTML error page (e.g. access denied)
            preview = ""
            try:
                preview = tmp_path.read_text(encoding="utf-8", errors="ignore")[:200]
            except Exception:
                pass
            tmp_path.unlink(missing_ok=True)
            if "Google Drive" in preview or "Access denied" in preview or "Sign in" in preview:
                return False, "Access denied. Make sure the Google Drive link is shared with 'Anyone with the link can view'.", 0
            return False, "The downloaded file is not a valid SQLite database (.db).", 0

        # Move into destination safely
        if dest.exists():
            backup = dest.parent / f"{dest.stem}_backup_{int(datetime.now().timestamp())}.db"
            try:
                shutil.copy2(dest, backup)
            except Exception:
                pass

        shutil.move(str(tmp_path), str(dest))
        return True, f"Successfully downloaded and verified database ({total_bytes / (1024*1024):.2f} MB)!", total_bytes

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return False, f"Connection error while downloading from Google Drive: {str(e)}", 0


def scan_local_gdrive_candidates(base_dir):
    """
    Search local Google Drive desktop drives, user downloads, and project directories
    for trendsense database files.
    """
    base = Path(base_dir).resolve()
    cands = []

    # Priority search locations
    search_dirs = [
        base,
        base.parent,
        Path.home() / "Downloads",
        Path.home() / "Desktop" / "trendsense",
        Path.home() / "Google Drive",
        Path.home() / "My Drive",
        Path("G:/My Drive"),
        Path("G:/"),
    ]

    seen = set()
    for d in search_dirs:
        if not d.exists():
            continue
        try:
            for pattern in ["trendsense*.db", "*.db"]:
                for p in d.glob(pattern):
                    p_str = str(p.resolve())
                    if p_str in seen or not p.is_file() or p.name.startswith("users"):
                        continue
                    seen.add(p_str)
                    size = p.stat().st_size
                    if size > 1000:
                        # Quick probe of tables
                        tables = []
                        rows = 0
                        try:
                            con = sqlite3.connect(p_str)
                            cur = con.cursor()
                            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                            if "google_trends" in tables:
                                rows = cur.execute("SELECT COUNT(*) FROM google_trends").fetchone()[0]
                            con.close()
                        except Exception:
                            pass

                        cands.append({
                            "path": p_str,
                            "name": p.name,
                            "size_mb": round(size / (1024 * 1024), 2),
                            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                            "has_google_trends": "google_trends" in tables,
                            "google_trends_rows": rows,
                        })
        except Exception:
            continue

    # Sort candidates by google_trends row count, then size
    cands.sort(key=lambda x: (x["google_trends_rows"], x["size_mb"]), reverse=True)
    return cands


def load_config(base_dir):
    p = Path(base_dir) / CONFIG_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(base_dir, cfg):
    p = Path(base_dir) / CONFIG_FILE
    try:
        p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass
