@echo off
cd /d "C:\Users\Mario\asgardmade-crew"
del /f /q ".git\index.lock" 2>nul
git add -A
git commit -m "Dark luxury UI + rewired agent prompts + inter-agent tasking + auto-approve + prompt self-rewrite"
git push
echo.
echo === Done! ===
pause
