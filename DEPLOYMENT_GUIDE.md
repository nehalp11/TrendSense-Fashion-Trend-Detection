# TrendSense Deployment Guide (Free 24/7 Cloud & Phone Access)

This guide shows you how to deploy **TrendSense** to the cloud so anyone—including you on your mobile phone anywhere—can access it via a live public web link (e.g., `https://trendsense.streamlit.app`).

---

## Option 1: Streamlit Community Cloud (Recommended · Free Forever · 24/7 Online)

Streamlit Community Cloud is 100% free and hosts Streamlit applications directly from GitHub.

### Step 1: Create a Free GitHub Account & Repository
1. Go to [https://github.com](https://github.com) and sign in (or create a free account).
2. Click the **+** icon in the top right and select **New repository**.
3. Name your repository (e.g., `trendsense-fashion-radar`).
4. Set it to **Public** or **Private**, and click **Create repository**.

### Step 2: Push Your TrendSense Code to GitHub
Open PowerShell or Command Prompt in your project folder (`c:\Users\PC\Downloads\trendsense_app\trendsense_app`) and run:
```bash
git init
git add .
git commit -m "Deploy TrendSense AI Fashion Atelier"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/trendsense-fashion-radar.git
git push -u origin main
```
*(Replace `<YOUR_GITHUB_USERNAME>` with your GitHub username)*

### Step 3: 1-Click Deploy on Streamlit Cloud
1. Go to [https://share.streamlit.io](https://share.streamlit.io) and click **Sign in with GitHub**.
2. Click **New app**.
3. Fill in the simple form:
   - **Repository:** `<YOUR_GITHUB_USERNAME>/trendsense-fashion-radar`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Click **Deploy!**

Within 1 to 2 minutes, your app is live at a URL like:
`https://<your-app-name>.streamlit.app`

You can open this URL on your phone's browser, bookmark it, and share it with your evaluators or boutique clients!

---

## Option 2: Instant Local Mobile Access (Right Now on Your Wi-Fi)

If your laptop and phone are connected to the same Wi-Fi:
1. Double-click `run.bat` on your computer.
2. Open your phone's camera and scan the QR code displayed in the sidebar under **📱 Open on Phone**.
3. Or type the mobile URL in Safari or Chrome on your phone:
   ```text
   http://192.168.1.37:8501
   ```

---

## Option 3: Instant Public Web Tunnel (ngrok / Cloudflare Tunnel)

If you want a public internet link immediately without pushing to GitHub:
1. In PowerShell, run:
   ```bash
   npx localtunnel --port 8501
   ```
2. It will output a public URL:
   ```text
   your url is: https://bright-silks-move.loca.lt
   ```
3. Open that link on your phone from anywhere in the world!
