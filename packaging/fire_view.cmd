@echo off
REM Nima's viewer. Runs from source, not from the customer build.
REM
REM The viewer reaches the cloud box using credentials on this machine, so it
REM is deliberately NOT part of anything a customer receives; the release gate
REM fails a build that contains it.
setlocal
set FIRE_OWNER_MODE=1
set PYTHONPATH=%~dp0..\src
start "" "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe" -m fire --view --owner
