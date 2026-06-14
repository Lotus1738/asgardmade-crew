@echo off
cd /d "C:\Users\Mario\asgardmade-crew"
del /f /q ".git\index.lock" 2>nul
git add -A
git commit -m "HUD redesign: ODIN throne room, 5-agent rooms, wandering system, flask icon, VAULT graphs, DEMO_IMAGES fix"
git push
echo.
echo === Done! ===
pause
