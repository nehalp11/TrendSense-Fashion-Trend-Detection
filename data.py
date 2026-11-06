"""
Data loading, scoring and sample data for TrendSense (no Streamlit imports).

Why the dashboard used to show nothing:  trend_scores had no Sg values (they were lost),
so every row was filtered out.  assemble_trends() now rebuilds Sg from the raw
google_trends table when that happens, and health() explains the state of the data.
"""
import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

TABLES = ["google_trends", "reddit_posts", "pinterest_images", "trend_scores", "ground_truth"]
STOP_TOKENS = {"these", "this", "just", "back", "wore", "obsessed", "what", "with", "from", "that"}


def infer_category(keyword, gt_df=None):
    """Categorize fashion keywords into practical merchandising groups."""
    if gt_df is not None and isinstance(gt_df, pd.DataFrame) and not gt_df.empty and "category" in gt_df.columns:
        match = gt_df[gt_df["keyword"] == keyword]
        if not match.empty and pd.notna(match.iloc[0]["category"]) and match.iloc[0]["category"]:
            return str(match.iloc[0]["category"])

    k = str(keyword).lower()
    if any(w in k for w in ['saree', 'kurti', 'lehenga', 'gown', 'coord', 'co-ord', 'suit', 'dress', 'skirt',
                           'shirt', 'pant', 'dupatta', 'palazzo', 'anarkali', 'kaftan', 'blouse', 'jacket']):
        return 'Garment'
    if any(w in k for w in ['diwali', 'eid', 'holi', 'navratri', 'festive', 'wedding', 'bridal', 'pooja', 'rakhi', 'durga']):
        return 'Festival'
    if any(w in k for w in ['streetwear', 'y2k', 'fusion', 'indo western', 'vintage', 'retro', 'minimalist',
                           'gorpcore', 'cargo', 'denim', 'blazer']):
        return 'Modern'
    if any(w in k for w in ['aesthetic', 'core', 'chic', 'boho', 'academia', 'cottagecore', 'pastel', 'grunge']):
        return 'Aesthetic'
    if any(w in k for w in ['print', 'embroidery', 'chikankari', 'bandhani', 'ajrakh', 'mirror work', 'zari',
                           'silk', 'cotton', 'linen', 'organza', 'velvet']):
        return 'Descriptor'
    return 'Trending Style'


def find_db(base):
    base = Path(base)
    if os.environ.get("TRENDSENSE_DB"):
        env_p = Path(os.environ["TRENDSENSE_DB"])
        if env_p.exists() and env_p.stat().st_size > 0:
            return str(env_p)

    cands = []
    # Project directories and common variations
    cands += [base / "trendsense.db", base / "trendsense (1).db", base / "trendsense (2).db"]
    try:
        cands += list(base.glob("trendsense*.db"))
    except Exception:
        pass
    cands += [base.parent / "trendsense.db", base.parent / "trendsense (1).db"]
    try:
        cands += list(base.parent.glob("trendsense*.db"))
    except Exception:
        pass
    cands += [Path.cwd() / "trendsense.db", Path.cwd().parent / "trendsense.db"]

    # Google Drive / Downloads / Desktop locations
    cands += [
        Path.home() / "Downloads" / "trendsense (1).db",
        Path.home() / "Downloads" / "trendsense (2).db",
        Path.home() / "Downloads" / "trendsense.db",
        Path.home() / "Google Drive" / "trendsense.db",
        Path.home() / "My Drive" / "trendsense.db",
        Path("G:/My Drive/trendsense.db"),
        Path.home() / "Desktop" / "trendsense" / "trendsense.db",
    ]

    valid = []
    seen = set()
    for c in cands:
        try:
            if c and c.exists() and c.is_file() and c.stat().st_size > 0:
                res_path = str(c.resolve())
                if res_path not in seen:
                    seen.add(res_path)
                    valid.append(c)
        except Exception:
            continue

    if not valid:
        return None

    # Sort to prioritize populated database files over 0-byte or 36KB empty stubs
    valid.sort(key=lambda p: p.stat().st_size, reverse=True)
    return str(valid[0])


def load(db_path):
    """Read every table we need. Missing tables or columns never crash; they come back empty."""
    con = sqlite3.connect(db_path)

    def table(name, cols):
        try:
            have = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
        except Exception:
            have = []
        if not have:
            return pd.DataFrame(columns=cols)
        use = [c for c in cols if c in have]
        df = pd.read_sql(f"SELECT {','.join(use)} FROM {name}", con)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        return df[cols]

    def count(name):
        try:
            return con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        except Exception:
            return 0

    out = {
        "trends": table("trend_scores", ["keyword", "sg", "sr", "sp", "breakthrough_week", "week_date"]),
        "google": table("google_trends", ["keyword", "week_date", "score"]),
        "reddit": table("reddit_posts", ["id", "subreddit", "title", "body", "upvotes", "created_utc"]),
        "gt": table("ground_truth", ["keyword", "category", "went_mainstream", "lag_weeks", "festival_related", "mainstream_platform", "confirmation_url"]),
        "counts": {n: count(n) for n in TABLES},
        "is_sample": False,
    }
    con.close()
    return out


def derive_sg(google):
    """Search acceleration per keyword, scaled 0-100 (same idea as the project's Sg formula)."""
    g = google.copy()
    g["week_date"] = pd.to_datetime(g["week_date"], errors="coerce")
    g["score"] = pd.to_numeric(g["score"], errors="coerce")
    g = g.dropna(subset=["week_date", "score"]).sort_values(["keyword", "week_date"])
    acc = {}
    for kw, grp in g.groupby("keyword"):
        s = grp["score"].to_numpy()
        if len(s) >= 3:
            acc[kw] = float((s[-1] - s[-2]) - (s[-2] - s[-3]))
    if not acc:
        return pd.Series(dtype=float)
    a = pd.Series(acc)
    lo, hi = a.min(), a.max()
    return ((a - lo) / (hi - lo) * 100).round(2) if hi > lo else a * 0 + 50.0


def assemble_trends(d, enrich_all=False):
    """Returns (trends_dataframe, sg_was_rebuilt)."""
    t = d["trends"].copy()
    for c in ("sg", "sr", "sp"):
        t[c] = pd.to_numeric(t[c], errors="coerce").fillna(0.0)
    rebuilt = False

    needs_rebuild = not (t.sg > 0).any() and not d["google"].empty
    google_kw_count = len(d["google"]["keyword"].unique()) if not d["google"].empty else 0
    should_enrich = enrich_all or (google_kw_count > len(t) * 2 and google_kw_count > 50)

    if (needs_rebuild or should_enrich) and not d["google"].empty:
        sg = derive_sg(d["google"])
        if not sg.empty:
            rebuilt = True
            latest = pd.to_datetime(d["google"]["week_date"], errors="coerce").max()
            base = pd.DataFrame({"keyword": sg.index, "sg": sg.values})

            # Clean out pure digit noise tokens and stop words from Reddit
            base = base[~base.keyword.astype(str).str.isdigit()]
            base = base[~base.keyword.astype(str).str.lower().isin(STOP_TOKENS)]

            rest = t.drop(columns=["sg"], errors="ignore").drop_duplicates("keyword")
            rest = rest[~rest.keyword.astype(str).str.isdigit()]
            rest = rest[~rest.keyword.astype(str).str.lower().isin(STOP_TOKENS)]
            t = base.merge(rest, on="keyword", how="outer")
            for c in ("sg", "sr", "sp"):
                t[c] = t[c].fillna(0.0)
            t["week_date"] = t["week_date"].fillna(str(latest.date()) if pd.notna(latest) else None)

    # Attach category
    gt = d.get("gt")
    t["category"] = t["keyword"].apply(lambda kw: infer_category(kw, gt))
    return t, rebuilt


def prepare(df):
    d = df.copy()
    for c in ["sg", "sr", "sp"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["score"] = (0.40 * d.sg + 0.35 * d.sr + 0.25 * d.sp).round(1)
    n = (d[["sg", "sr", "sp"]] > 40).sum(axis=1)
    d["level"] = n.map({3: "HIGH", 2: "MEDIUM"}).fillna("LOW")
    week = pd.to_datetime(d["week_date"], errors="coerce")
    bt = pd.to_datetime(d["breakthrough_week"], errors="coerce")
    d["expected"] = bt.fillna(week + pd.Timedelta(weeks=6))
    # Rebase: if expected date has already passed, shift to today + 6 weeks
    _today = pd.Timestamp("today").normalize()
    d["expected"] = d["expected"].apply(
        lambda x: _today + pd.Timedelta(weeks=6) if pd.notna(x) and x < _today else x
    )
    d = d[d.score > 0].sort_values("score", ascending=False)
    d = d.drop_duplicates("keyword").reset_index(drop=True)
    top = d.score.max() if len(d) else 1
    d["heat"] = (d.score / top * 100).round(0)
    if "category" not in d.columns:
        d["category"] = d["keyword"].apply(infer_category)
    return d


def sample_data(today=None):
    """Clearly-labelled demo data so the dashboard is never empty."""
    rnd = random.Random(7)
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    rows = [("pastel coord set", 78, 65, 58), ("mirror work coord", 66, 52, 12), ("kerala fashion", 87, 0, 48),
            ("linen kurta set", 47, 44, 43), ("chikankari kurti", 44, 41, 10), ("bandhani print outfit", 52, 30, 0),
            ("indo western fusion outfit", 35, 22, 45), ("anarkali gown", 8, 0, 61), ("saree styling", 12, 0, 38),
            ("block print dupatta", 58, 0, 0), ("cotton coord set", 41, 25, 0), ("festive lehenga", 31, 0, 0)]
    trends = pd.DataFrame(rows, columns=["keyword", "sg", "sr", "sp"])
    trends["breakthrough_week"] = None
    trends["week_date"] = str(monday)
    trends["category"] = trends["keyword"].apply(infer_category)
    g = []
    for kw, sg, _, _ in rows:
        if sg <= 0:
            continue
        start = max(5.0, sg * 0.3)
        for i in range(12):
            v = start + (sg - start) * (i / 11) + rnd.uniform(-3, 3)
            g.append((kw, str(monday - timedelta(weeks=11 - i)), round(min(100, max(0, v)), 1)))
    google = pd.DataFrame(g, columns=["keyword", "week_date", "score"])
    gt = pd.DataFrame({"keyword": [r[0] for r in rows], "went_mainstream": [1] * 9 + [0] * 3,
                       "category": [infer_category(r[0]) for r in rows],
                       "lag_weeks": [6, 7, 6, 6, 7, 6, 6, 7, 6, 0, 0, 0], "festival_related": [0] * 12})
    sample_reddit = pd.DataFrame([
        (1, "IndianFashionAddicts", "obsessed rn with this pastel coord set just found it everyone is wearing it", 45),
        (2, "IndianFashionAddicts", "where to buy this mirror work dupatta just dropped love it need this now", 67),
        (3, "IndianFashion", "currently loving this block print kurti just discovered it this week", 34),
        (4, "IndianFashion", "anyone else obsessed with sharara sets rn just got one and im not okay", 89),
        (5, "IndianFashionAddicts", "just dropped this ikat coord everyone needs it where to buy this now", 56),
    ], columns=["id", "subreddit", "title", "upvotes"])
    counts = {"google_trends": len(google), "reddit_posts": len(sample_reddit), "pinterest_images": 430,
              "trend_scores": len(trends), "ground_truth": len(gt)}
    return {"trends": trends, "google": google, "reddit": sample_reddit, "gt": gt, "counts": counts, "is_sample": True}


def health(d, db_path, rebuilt):
    """A plain table the team can read to see why the dashboard looks the way it does."""
    ok, warn, bad = "✅", "⚠️", "❌"
    if d is None:
        return pd.DataFrame([(bad, "Database file", "trendsense.db was not found. Put it next to app.py or upload it.")],
                            columns=["", "Check", "Details"])
    c, t = d["counts"], d["trends"]
    sg_n = int((pd.to_numeric(t["sg"], errors="coerce").fillna(0) > 0).sum())
    sp_n = int((pd.to_numeric(t["sp"], errors="coerce").fillna(0) > 0).sum())
    sr_n = int((pd.to_numeric(t["sr"], errors="coerce").fillna(0) > 0).sum())
    last = pd.to_datetime(d["google"]["week_date"], errors="coerce").max() if not d["google"].empty else None
    rows = [
        (ok, "Database file", str(db_path)),
        (ok if c["google_trends"] else bad, "google_trends rows", f"{c['google_trends']:,}"),
        (ok if c["trend_scores"] else warn, "trend_scores rows", f"{c['trend_scores']:,}"),
        (ok if sg_n else (warn if rebuilt else bad), "Search scores (Sg)",
         f"{sg_n} saved" + ("; rebuilt live from google_trends" if rebuilt else "")),
        (ok if sp_n else warn, "Visual scores (Sp)", f"{sp_n} Pinterest clusters scored"),
        (ok if sr_n else warn, "Community scores (Sr)", f"{sr_n} scored" + ("" if sr_n else " (Reddit not connected yet)")),
        (ok if c["ground_truth"] else warn, "ground_truth rows", f"{c['ground_truth']:,}"),
        (ok if last is not None and pd.notna(last) else warn, "Latest Google Trends week",
         str(last.date()) if last is not None and pd.notna(last) else "unknown"),
    ]
    return pd.DataFrame(rows, columns=["", "Check", "Details"])
