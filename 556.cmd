@echo off
REM 556 Production - isolated Hermes instance launcher (own engine copy + own HERMES_HOME).
set "HERMES_HOME=%~dp0home"
"%~dp0vendor\hermes-agent\.venv\Scripts\hermes.exe" %*
