@echo off
REM Open the Live2D avatar as a frameless app-mode window.
REM Requires the bridge running (node live2d-bridge.mjs in ui\live2d).
start "" chrome --new-window --app=http://127.0.0.1:19200/index.html --window-size=450,650
