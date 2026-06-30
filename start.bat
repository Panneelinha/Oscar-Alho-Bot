@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
title Oscar Alho - bot do Discord
echo ============================================
echo   Oscar Alho - bot do Discord
echo   Feche esta janela para desligar o bot.
echo ============================================
echo.
:loop
python bot.py
echo.
echo [%date% %time%] O bot parou. Reiniciando em 5s... (feche a janela para sair)
timeout /t 5 /nobreak >nul
goto loop
