@echo off
REM Desktop pet: transparent always-on-top Live2D girl.
REM Requires the bridge running (node live2d-bridge.mjs in ui\live2d).
cd /d D:\dev\556_production\ui\pet
start "" .\node_modules\electron\dist\electron.exe .
