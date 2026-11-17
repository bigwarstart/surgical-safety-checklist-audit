@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo [HATA] Kurulum yapilmamis. Once kurulum.bat dosyasini calistirin.
  pause
  exit /b 1
)
if not exist config.ini (
  echo [HATA] config.ini yok. config.ini.ornek dosyasini kopyalayip config.ini yapin ve doldurun.
  pause
  exit /b 1
)
venv\Scripts\python.exe app.py
pause
