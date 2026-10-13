@echo off
REM Open the Live2D avatar as a frameless app-mode window (served by 556d).
start "" chrome --new-window --app=http://127.0.0.1:55600/index.html --window-size=450,650
