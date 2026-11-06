"""Run with:  python tests/run_tests.py   (no Streamlit needed)"""
import os, re, sqlite3, sys, tempfile, time
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
import auth, data as dm
from i18n import TR, LANGS, translator

passed = 0
def check(cond, label):
    global passed
    assert cond, "FAILED: " + label
    passed += 1

# ---------------------------------------------------------------- accounts
tmp = tempfile.mkdtemp()
auth.init(os.path.join(tmp, "users.db"))
u1, e = auth.register("Anita", "secret-pass1", "Anita Rao", "Anita Boutique", "kn")
check(e is None and u1["role"] == "owner" and u1["lang"] == "kn", "new user gets owner role, language kept")
u2, e = auth.register("ravi_01", "another-pass", "Ravi", "Ravi Tex", "en")
check(e is None and u2["role"] == "owner", "second user is also an owner")
check(auth.register("ANITA", "secret-pass1", "x", "y")[1] == "err_taken", "usernames are case-insensitive unique")
check(auth.register("bob", "short", "B", "S")[1] == "err_pw", "short password rejected")
check(auth.register("b", "long-enough-pw", "B", "S")[1] == "err_user", "too-short username rejected")
check(auth.register("bad name!", "long-enough-pw", "B", "S")[1] == "err_user", "illegal characters rejected")
check(auth.register("carol", "long-enough-pw", "", "S")[1] == "err_fields", "empty field rejected")

user, e = auth.authenticate("anita", "secret-pass1")
check(user and user["id"] == u1["id"] and e is None, "correct login works (any letter case)")
check(auth.authenticate("anita", "wrong")[1] == "err_login", "wrong password refused")
check(auth.authenticate("nobody", "whatever1")[1] == "err_login", "unknown user refused")
check(auth.authenticate("x' OR '1'='1", "x' OR '1'='1")[1] == "err_login", "SQL injection attempt refused")
check(auth.count_users() == 2, "injection attempt created/changed nothing")

raw = open(os.path.join(tmp, "users.db"), "rb").read()
check(b"secret-pass1" not in raw and b"another-pass" not in raw, "no plaintext password anywhere in the file")
with sqlite3.connect(os.path.join(tmp, "users.db")) as c:
    salts = [r[0] for r in c.execute("SELECT salt FROM users")]
check(len(set(salts)) == 2, "every user has a different salt")

for _ in range(5):
    auth.authenticate("ravi_01", "bad-guess")
check(auth.authenticate("ravi_01", "another-pass")[1] == "err_locked", "5 wrong tries lock the account, even for the right password")
check(auth.authenticate("anita", "secret-pass1")[0] is not None, "lockout is per-user (other users unaffected)")
ok, _ = auth.set_password("ravi_01", "brand-new-pass")
check(ok and auth.authenticate("ravi_01", "brand-new-pass")[0] is not None, "admin reset clears lock and sets new password")
check(auth.authenticate("ravi_01", "another-pass")[1] == "err_login", "old password no longer works")

auth.set_watchlist(u1["id"], ["pastel coord set", "saree styling"])
check(sorted(auth.get_watchlist(u1["id"])) == ["pastel coord set", "saree styling"], "watchlist saved")
check(auth.get_watchlist(u2["id"]) == [], "watchlists are private per user")
auth.set_watchlist(u1["id"], ["saree styling"])
check(auth.get_watchlist(u1["id"]) == ["saree styling"], "watchlist can shrink")
auth.update_pref(u1["id"], lang="hi", lead_weeks=5)
u, _ = auth.authenticate("anita", "secret-pass1")
check(u["lang"] == "hi" and u["lead_weeks"] == 5, "language + supplier lead time persist")
check(all("hash" not in k and "salt" not in k for k in auth.list_users()[0]), "user list never exposes hashes")

# ------------------------------------------------- data: the 'no results' bug
def make_db(path, with_sg):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE google_trends (id INTEGER PRIMARY KEY, keyword TEXT, week_date TEXT, score REAL)")
    c.execute("CREATE TABLE trend_scores (keyword TEXT PRIMARY KEY, sg REAL, sr REAL, sp REAL, week_date TEXT)")
    rows = []
    for kw, slope in [("kerala fashion", 6), ("coord set", 3), ("saree", 0), ("kurti", -2)]:
        for w in range(12):
            rows.append((kw, f"2026-07-{w+1:02d}", 30 + slope * w + (w * w * 0.2 if kw == "kerala fashion" else 0)))
    c.executemany("INSERT INTO google_trends (keyword,week_date,score) VALUES (?,?,?)", rows)
    sg = 80.0 if with_sg else None
    c.executemany("INSERT INTO trend_scores VALUES (?,?,?,?,?)",
                  [("anarkali gown", None, None, 100.0, "2026-09-25"), ("chikankari kurti", None, None, 10.0, "2026-09-25"),
                   ("kerala fashion", sg, 0.0, 0.0, "2026-09-25")])
    c.commit(); c.close()

p = os.path.join(tmp, "lost_sg.db"); make_db(p, with_sg=False)
d = dm.load(p)
check((pd.to_numeric(d["trends"].sg, errors="coerce").fillna(0) > 0).sum() == 0, "setup: the DB really has no Sg (the bug)")
raw, rebuilt = dm.assemble_trends(d)
t = dm.prepare(raw)
check(rebuilt, "Sg is rebuilt from google_trends when missing")
check(len(t) >= 3 and "kerala fashion" in t.keyword.values, "dashboard now has results where it had none")
check("anarkali gown" in t.keyword.values, "existing Pinterest (Sp) rows are kept")
check(t.iloc[0].keyword == "kerala fashion", "fastest-accelerating style ranks first")
check(t.expected.notna().all(), "every trend gets an expected-date")

p2 = os.path.join(tmp, "ok_sg.db"); make_db(p2, with_sg=True)
raw, rebuilt = dm.assemble_trends(dm.load(p2))
check(not rebuilt, "saved Sg is used as-is when it exists")

p3 = os.path.join(tmp, "empty.db"); sqlite3.connect(p3).close()
d3 = dm.load(p3)
raw, rebuilt = dm.assemble_trends(d3)
check(dm.prepare(raw).empty, "empty database gives an empty result, not a crash")
check(len(dm.health(d3, p3, False)) >= 5, "health table works on an empty database")
check("not found" in dm.health(None, None, False).iloc[0]["Details"], "health table explains a missing database")

s = dm.sample_data(date(2026, 10, 14)); st_ = dm.prepare(s["trends"])
check(len(st_) == 12 and set(st_.level) == {"HIGH", "MEDIUM", "LOW"}, "sample data covers all three confidence levels")
check(s["is_sample"] and not d["is_sample"], "sample data is flagged as sample")

# ------------------------------------------------------------ translations
en = set(TR["en"])
ph = lambda s: sorted(re.findall(r"\{(\w+)\}", s))
for lang, tr in TR.items():
    check(set(tr) == en, f"{lang}: has exactly the same keys as English")
    for k, v in tr.items():
        check(v.strip() and ph(v) == ph(TR["en"][k]), f"{lang}.{k}: not empty, placeholders match")
check(set(LANGS.values()) == set(TR), "every language in the picker has translations")
check("Anita" in translator("kn")("welcome", name="Anita"), "welcome message formats the name")
print(f"\n{passed} checks passed - ALL OK")
