@echo off
chcp 65001 >nul
echo ======================================================================
echo ✈️ KHỞI ĐỘNG HERMES VISION EXTRACTOR (LUFTHANSA CARGO CMS HELPER)
echo ======================================================================
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
"C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe" main.py --show-manager
pause
