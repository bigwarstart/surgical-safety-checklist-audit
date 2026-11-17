@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Guvenli Cerrahi Denetimi kurulumu ===
echo.

rem --- Python'u bul: once "py" baslaticisi, sonra "python" ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo [HATA] Bu bilgisayarda Python bulunamadi.
  echo.
  echo Python kuruluysa yolunu asagidaki satira yazin,
  echo ornek:  set "PY=C:\Python312\python.exe"
  echo ya da https://www.python.org adresinden Python kurun
  echo ^(kurulumda "Add python.exe to PATH" kutusunu isaretleyin^).
  pause
  exit /b 1
)
echo Kullanilan Python: %PY%
%PY% --version
echo.

%PY% -m venv venv
if not exist venv\Scripts\python.exe (
  echo [HATA] Sanal ortam olusturulamadi.
  pause
  exit /b 1
)
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo [HATA] Paketler kurulamadi. Internet baglantisini kontrol edin.
  pause
  exit /b 1
)
if not exist config.ini copy config.ini.ornek config.ini >nul

echo.
echo Guvenlik duvarinda 5051 portu aciliyor...
netsh advfirewall firewall add rule name="Guvenli Cerrahi Denetimi 5051" dir=in action=allow protocol=TCP localport=5051 >nul 2>nul
if errorlevel 1 echo [UYARI] Port acilamadi. Bu dosyayi sag tik - "Yonetici olarak calistir" ile tekrar calistirin.

echo.
echo ============================================================
echo Kurulum bitti.
echo 1) config.ini dosyasini acip veritabani bilgilerini girin
echo 2) baslat.bat ile calistirin
echo ============================================================
pause
