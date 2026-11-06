@echo off
chcp 65001 >nul
cd /d "C:\Users\admin\Documents\deepseek-harness\default-workspace\dsh-persona-curiosity"
echo ========================================
echo   人格同步：云端 QQ + 云端 B站 → 本地
echo ========================================
echo.
node sync-persona.cjs
echo.
echo 按任意键关闭...
pause >nul
