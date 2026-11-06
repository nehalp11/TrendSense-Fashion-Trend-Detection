# TrendSense - AI Multimodal Fashion Trend Radar

Spot emerging Indian fashion trends, garments, and aesthetics 6+ weeks before they hit major retail stores.

---

## 🚀 Quick Start (Windows)

1. Double-click **`run.bat`** (or open terminal and run `pip install -r requirements.txt` followed by `streamlit run app.py`).
2. Your browser will open at `http://localhost:8501`.
3. Sign in or click **Create account**. The first created account automatically receives the **admin** role.
4. *Existing admin account:* username `hhh` (already initialized in `users.db`).

---

## ☁️ Google Drive Connection & Data Sync

TrendSense supports two seamless ways to connect Google Drive data:

1. **Direct Google Drive Link Sync**:
   - In the **☁️ Google Drive** tab, paste any shareable Google Drive link (e.g., `https://drive.google.com/file/d/1.../view?usp=sharing`) or a File ID.
   - Click **⚡ Download & Sync from Google Drive**. TrendSense downloads the database file, verifies table integrity, saves it locally, and updates your radar live!
2. **Auto-Detected Local Databases**:
   - The app automatically scans Google Drive Desktop (`G:\My Drive\...`, `Google Drive`), Downloads (`trendsense (1).db`, etc.), and project directories.
   - It lists detected databases with file sizes and row counts, allowing 1-click connection.

---

## 🎨 Dashboard Features

- **⚡ Live Radar & Style of the Week**: Spotlight card for the #1 accelerating trend with sparkline velocity, early warning horizon, and action recommendations.
- **📊 Visual Trend Matrix**: Interactive bubble chart plotting Search Acceleration ($S_g$) against Multimodal Trend Score ($T$) with category color coding and confidence sizing.
- **👗 Merchandising Categories**: Filter across Garments, Festive & Ethnic, Modern & Streetwear, Aesthetics, and Fabrics/Prints.
- **🔍 Deep Dive & Multi-Trend Studio**: Compare up to 4 styles simultaneously over time with multi-curve time-series graphs and breakdown of multimodal signals (Google Search, Reddit Community, and Pinterest Visuals).
- **📌 Smart Watchlist & Supplier Lead-Time Planner**: Set supplier delivery lead times (0–12 weeks) to automatically calculate exact **Order By** deadlines with 1-click CSV export.
- **🌐 9 Indian Languages**: Full native translations for English, Hindi (हिन्दी), Kannada (ಕನ್ನಡ), Tamil (தமிழ்), Telugu (తెలుగు), Malayalam (മലയാളം), Marathi (मराठी), Bengali (বাংলা), and Gujarati (ગુજરાતી).
- **🛠 Admin & Data Health Console**: View table row counters, verify database integrity, inspect signal recalculations, and manage user accounts.

---

## 🧪 Testing

```bash
python tests/run_tests.py     # 739 unit tests (accounts, data scoring, translations)
python tests/app_smoke.py     # 26 page-level end-to-end user journeys
```

---

## 📁 Architecture

- `app.py`: Streamlit frontend with modern glassmorphism design, interactive Plotly charts, and multilingual tabs.
- `gdrive.py`: Google Drive direct cloud download, local sync scanner, and connection config manager.
- `data.py`: Smart database discovery, noise token filtering, category inference, and multimodal trend scoring.
- `auth.py`: Salted PBKDF2 user authentication, private watchlists, and lead-time preferences.
- `theme.css`: Modern UI design system with elevated cards, gradient accents, and responsive layout.
- `i18n.py`: Multilingual dictionary supporting 9 languages.
