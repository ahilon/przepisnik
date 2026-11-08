@echo off
setlocal
pushd "%~dp0.." || exit /b 1
uv run ruff check .
if errorlevel 1 goto failed
uv run ruff format --check .
if errorlevel 1 goto failed
uv run python -m mypy src
if errorlevel 1 goto failed
rem Checkov reads .checkov.yaml; the module form avoids blocked tool executables.
uvx --python 3.12 --from checkov==3.4.3 python -m checkov.main
if errorlevel 1 goto failed
popd
exit /b 0

:failed
set "check_result=%errorlevel%"
popd
exit /b %check_result%
