@echo off
cd /d "C:\Users\Mario\asgardmade-crew"
del /f /q ".git\index.lock" 2>nul
git add -A
git commit -m "Fix display names/icon, add room scene canvas, ODIN upgrade commands"
git push
echo.
echo === Done! ===
pause
