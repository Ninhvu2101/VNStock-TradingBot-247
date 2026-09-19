@echo off
title MyAgent - Bot Trading Chung Khoan Viet Nam 24/7 (@NinhVNStock_bot)
chcp 65001 >nul
cd /d "D:\MyAgent"

set "PYTHON_EXE=C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo ===================================================================
echo     MYAGENT AUTO-TRADING CHỨNG KHOÁN VIỆT NAM 24/7
echo     Telegram: @NinhVNStock_bot
echo     Tự động khôi phục khi gặp sự cố (Auto-Restart Guard)
echo ===================================================================

:LOOP
echo [%date% %time%] Đang khởi động hệ thống Bot Trading 24/7...
"%PYTHON_EXE%" "D:\MyAgent\5. bot trading\run_bot_247.py"

echo.
echo [CẢNH BÁO] Tiến trình đã dừng lại hoặc gặp lỗi.
echo Hệ thống sẽ tự động khởi động lại sau 5 giây...
timeout /t 5 /nobreak >nul
goto LOOP
