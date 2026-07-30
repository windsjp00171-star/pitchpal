@echo off
REM 在 Windows 上把 PitchPal 打包成獨立 EXE（雙擊 dist\PitchPal\PitchPal.exe 即可執行，不需另外安裝 Python）。
REM 使用方式：在專案資料夾內直接雙擊本檔案，或在命令提示字元執行 build_exe.bat

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo [錯誤] 找不到 python，請先安裝 Python 3.11（https://www.python.org/downloads/）並勾選 "Add to PATH"。
    pause
    exit /b 1
)

echo === 建立打包用虛擬環境 (.build-venv) ===
python -m venv .build-venv
call .build-venv\Scripts\activate.bat

echo === 安裝套件（第一次會花幾分鐘） ===
pip install --upgrade pip
pip install -r requirements-build.txt

echo === 執行 PyInstaller 打包 ===
pyinstaller --noconfirm PitchPal.spec

echo.
echo === 打包完成 ===
echo 執行檔在 dist\PitchPal\PitchPal.exe
echo.
echo 重要：請自行下載 ffmpeg.exe（https://www.gyan.dev/ffmpeg/builds/ 選 essentials build 內的 bin\ffmpeg.exe），
echo 放到 dist\PitchPal\ 資料夾（跟 PitchPal.exe 同一層），才能使用「影片轉音頻」與「輸出 MP3」功能。
echo.
pause
