@echo off
title TrendSense AI Fashion Atelier
cd /d "%~dp0"

echo =========================================================================
echo   ✦ TRENDSENSE - AI FASHION ATELIER & TREND DETECTION RADAR
echo =========================================================================
echo   Laptop Browser:  http://localhost:8501
echo   Mobile Phone:    http://192.168.1.37:8501
echo.
echo   [Tip: Connect your phone to the same Wi-Fi network and open the
echo         Mobile Phone link above in Chrome or Safari!]
echo =========================================================================
echo.

python -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501
pause
