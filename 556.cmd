@echo off
REM 556 Production - isolated Hermes instance launcher.
REM Own engine copy + own HERMES_HOME (production install is never touched).
set "HERMES_HOME=D:\dev\556_production\home"
"D:\dev\556_production\hermes-agent\.venv\Scripts\hermes.exe" %*
