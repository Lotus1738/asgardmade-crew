@echo off
cd /d "C:\Users\Mario\asgardmade-crew"
del /f /q ".git\index.lock" 2>nul
git add -A
git commit -m "Add agent idle animations, waving interactions, ODIN voice interface"
git push
echo.
echo === Done! ===
pause
