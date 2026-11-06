"""
Plays user journeys against app.py using a stand-in for Streamlit (the real one isn't
installable offline).  It checks the page logic end-to-end: login, data, watchlist, languages.
Run with:  python tests/app_smoke.py
"""
import os, re, sqlite3, sys, tempfile, types
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import pandas as pd

class StopApp(Exception): pass
class RerunApp(Exception): pass
class Any:
    def __getattr__(self, n): return Any()
    def __call__(self, *a, **k): return Any()
    def __iter__(self): return iter(())

class SS(dict):
    __getattr__ = dict.get
    def __setattr__(self, k, v): self[k] = v

LOG, SCRIPT, SUBMIT, BUTTONS, FLAGS = [], {}, set(), set(), {"rerun": False}
RENDERED, WIDGET_KEYS = set(), set()

class FakeSt:
    def __init__(self): self.session_state = SS(); self.sidebar = self
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def _val(self, key, label, default):
        for k in (key, label):
            if k is not None and k in SCRIPT: return SCRIPT[k]
        return default
    # ---- output widgets: just record what the user would see
    def _rec(kind):
        def f(self, text="", *a, **k): LOG.append((kind, str(text))); return Any()
        return f
    markdown = _rec("md"); caption = _rec("caption"); info = _rec("info"); warning = _rec("warning")
    error = _rec("error"); success = _rec("success"); latex = _rec("latex"); metric = _rec("metric")
    def dataframe(self, df, *a, **k): LOG.append(("df", "|".join(map(str, df.columns)) + f"|rows={len(df)}"))
    def plotly_chart(self, *a, **k): LOG.append(("chart", ""))
    def download_button(self, label, *a, **k): LOG.append(("download", label)); return False
    def progress(self, v, text=""): LOG.append(("progress", text))
    def divider(self): pass
    def write(self, *a, **k): pass
    def set_page_config(self, **k): pass
    def cache_data(self, *a, **k):
        return a[0] if a and callable(a[0]) else (lambda f: f)
    # ---- layout
    def columns(self, spec, **k): return [self] * (spec if isinstance(spec, int) else len(spec))
    def tabs(self, labels): LOG.append(("tabs", list(labels))); return [self] * len(labels)
    def form(self, key): return self
    def expander(self, *a, **k): return self
    # ---- inputs
    def text_input(self, label, key=None, **k):
        if key: RENDERED.add(key); WIDGET_KEYS.add(key)
        v = self._val(key, label, self.session_state.get(key, "") if key else "")
        if key: self.session_state[key] = v
        return v
    def form_submit_button(self, label, **k):
        if label in SUBMIT: SUBMIT.discard(label); return True
        return False
    def button(self, label, **k):
        if label in BUTTONS: BUTTONS.discard(label); return True
        return False
    def selectbox(self, label, options, index=0, key=None, on_change=None, **k):
        if key: RENDERED.add(key); WIDGET_KEYS.add(key)
        options = list(options)
        if key in SCRIPT:
            self.session_state[key] = SCRIPT[key]
        if key and key in self.session_state and self.session_state[key] in options \
                and options.index(self.session_state[key]) != index:
            if on_change: on_change(); FLAGS["rerun"] = True
            return self.session_state[key]
        v = options[index]
        if key: self.session_state[key] = v
        return v
    def multiselect(self, label, options, default=None, key=None, **k):
        if key: RENDERED.add(key); WIDGET_KEYS.add(key)
        options = list(options)
        if key and key in SCRIPT: self.session_state[key] = SCRIPT[key]
        v = self.session_state[key] if key and key in self.session_state else (default or [])
        bad = [x for x in v if x not in options]
        assert not bad, f"multiselect '{label}' holds values not in options: {bad}  (real Streamlit would crash)"
        if key: self.session_state[key] = v
        return list(v)
    def slider(self, label, lo, hi, value=None, key=None, **k):
        if key: RENDERED.add(key); WIDGET_KEYS.add(key)
        v = self._val(key, label, self.session_state.get(key, value))
        if key: self.session_state[key] = v
        return v
    def toggle(self, label, value=False, key=None, **k):
        if key: RENDERED.add(key); WIDGET_KEYS.add(key)
        v = self._val(key, label, self.session_state.get(key, value))
        if key: self.session_state[key] = v
        return v
    def file_uploader(self, *a, **k): return None
    def stop(self): raise StopApp()
    def rerun(self): raise RerunApp()

st = FakeSt()
sys.modules["streamlit"] = st
px = types.ModuleType("plotly.express")
px.bar = px.line = lambda *a, **k: Any()
plotly = types.ModuleType("plotly"); plotly.express = px
sys.modules["plotly"], sys.modules["plotly.express"] = plotly, px

# ------------------------------------------------------------------ test data
tmp = tempfile.mkdtemp()
os.environ["TRENDSENSE_USERS_DB"] = os.path.join(tmp, "users.db")
db = os.path.join(tmp, "trendsense.db")
c = sqlite3.connect(db)
c.execute("CREATE TABLE google_trends (id INTEGER PRIMARY KEY, keyword TEXT, week_date TEXT, score REAL)")
c.execute("CREATE TABLE trend_scores (keyword TEXT PRIMARY KEY, sg REAL, sr REAL, sp REAL, week_date TEXT)")
for kw, slope in [("kerala fashion", 6), ("coord set", 3), ("saree", 1), ("kurti", -2)]:
    for w in range(12):
        c.execute("INSERT INTO google_trends (keyword,week_date,score) VALUES (?,?,?)",
                  (kw, f"2026-07-{w+1:02d}", 30 + slope * w + (w * w * 0.3 if kw == "kerala fashion" else 0)))
c.executemany("INSERT INTO trend_scores VALUES (?,?,?,?,?)",     # note: NO Sg saved (the real bug)
              [("anarkali gown", None, None, 100.0, "2026-09-25"), ("chikankari kurti", None, None, 10.0, "2026-09-25")])
c.commit(); c.close()
os.environ["TRENDSENSE_DB"] = db

import auth
from i18n import translator
SRC = (APP / "app.py").read_text(encoding="utf-8")

def prune():
    for k in list(st.session_state):
        if k in WIDGET_KEYS and k not in RENDERED:
            del st.session_state[k]

def run():
    for _ in range(8):
        LOG.clear(); FLAGS["rerun"] = False; RENDERED.clear()
        try:
            exec(compile(SRC, "app.py", "exec"), {"__name__": "__main__", "__file__": str(APP / "app.py")})
        except StopApp:
            pass
        except RerunApp:
            prune(); continue
        prune()
        if FLAGS["rerun"]: continue
        return
    raise AssertionError("page keeps rerunning forever")

text = lambda: "\n".join(x[1] if isinstance(x[1], str) else " ".join(x[1]) for x in LOG)
ok = 0
def check(cond, label):
    global ok
    assert cond, "FAILED: " + label + "\n--- page text ---\n" + text()[:1500]
    ok += 1

# ---- 1. a visitor who is not signed in sees only the login page
run()
check(st.session_state["user"] is None, "visitor is not signed in")
check("Trend Radar" in text() and any(k == "tabs" and "Sign in" in v for k, v in LOG), "login page shows with Sign in / Create account tabs")
check("Likely to reach big retailers" not in text(), "no trend data is shown before login")

# ---- 2. register -> lands on the dashboard WITH RESULTS (Sg was missing in the DB)
SCRIPT.update(up_name="Anita Rao", up_shop="Anita Boutique", up_user="anita", up_pass="secret-pass1")
SUBMIT.add("Create my account"); run()
u = st.session_state["user"]
check(u and u["role"] == "owner", "newly registered user gets owner role (not auto-admin)")
check("Welcome, Anita Rao!" in text(), "welcome message shown")
check("kerala fashion" in text(), "dashboard shows results (Sg rebuilt from google_trends)")
check("anarkali gown" in text(), "Pinterest-only styles also appear")
check("SAMPLE" not in text(), "real data is used, not the sample")
check(not any(k == "tabs" and any("Admin" in x for x in v) for k, v in LOG), "owner does NOT see admin tab on first register")

# promote Anita to admin directly in the DB (simulates developer action)
import sqlite3 as _test_sqlite3
with _test_sqlite3.connect(os.environ["TRENDSENSE_USERS_DB"]) as _uc:
    _uc.execute("UPDATE users SET role='admin' WHERE username='anita'")
st.session_state["user"]["role"] = "admin"
u = st.session_state["user"]; run()
check(any(k == "tabs" and any("Admin" in x for x in v) for k, v in LOG), "admin sees the Admin tab after developer promotion")
check(any(k == "df" and "Check" in v for k, v in LOG), "data-health table is shown to the admin")

# ---- 3. watchlist + supplier lead time are saved to the account
SCRIPT.update(watch_sel=["kerala fashion", "anarkali gown"], lead_w=4); run()
check(sorted(auth.get_watchlist(u["id"])) == ["anarkali gown", "kerala fashion"], "watchlist saved to the database")
check(any(k == "df" and "Order by" in v for k, v in LOG), "watchlist table has the 'Order by' column")
check(auth.authenticate("anita", "secret-pass1")[0]["lead_weeks"] == 4, "supplier lead time saved")

# ---- 4. switch to Hindi: page changes and the choice is remembered
SCRIPT["lang_pick_side"] = "हिन्दी"; run()
check(st.session_state["lang"] == "hi", "language switched to Hindi")
check("स्वागत है, Anita Rao!" in text(), "welcome message now in Hindi")
check(any(k == "tabs" and "🏠 इस हफ़्ते" in v for k, v in LOG), "tab names now in Hindi")
check(auth.authenticate("anita", "secret-pass1")[0]["lang"] == "hi", "language choice saved to the account")

# ---- 5. sign out, wrong password, then the right one
t = translator("hi")
BUTTONS.add(t("logout")); run()
check(st.session_state["user"] is None, "sign out works")
SCRIPT.update(in_user="anita", in_pass="not-my-password"); SUBMIT.add(t("btn_signin")); run()
check(any(k == "error" and v == t("err_login") for k, v in LOG), "wrong password shows an error (in Hindi)")
check(st.session_state["user"] is None, "wrong password does not sign in")
SCRIPT["in_pass"] = "secret-pass1"; SUBMIT.add(t("btn_signin")); run()
check(st.session_state["user"] and st.session_state["lang"] == "hi", "right password signs in with saved language")
check(sorted(auth.get_watchlist(st.session_state["user"]["id"])) == ["anarkali gown", "kerala fashion"], "watchlist survives sign-out/sign-in")

# ---- 6. a normal business owner: no Admin tab
BUTTONS.add(t("logout")); run()
for k in ("in_user", "in_pass", "watch_sel", "lang_pick_side"): SCRIPT.pop(k, None)
st.session_state["lang"] = "en"; st.session_state.pop("lang_pick_side", None); st.session_state.pop("lang_pick_main", None)
SCRIPT.update(up_name="Ravi", up_shop="Ravi Tex", up_user="ravi", up_pass="another-pass")
SUBMIT.add("Create my account"); run()
check(st.session_state["user"]["role"] == "owner", "second user is a normal owner")
check(not any(k == "tabs" and any("Admin" in x for x in v) for k, v in LOG), "owner does NOT see the Admin tab")
check(auth.get_watchlist(st.session_state["user"]["id"]) == [], "owner starts with an empty private watchlist")

# ---- 7. no database at all -> clearly-labelled sample data instead of a blank page
os.environ["TRENDSENSE_DB"] = os.path.join(tmp, "missing.db"); os.chdir(tmp)
import data as dm
dm.find_db = lambda base: None
st.session_state.pop("watch_sel", None); run()
check("SAMPLE" in text() and "pastel coord set" in text(), "with no database the page shows labelled sample data, not a blank screen")

print(f"\n{ok} page-level checks passed - ALL OK")
