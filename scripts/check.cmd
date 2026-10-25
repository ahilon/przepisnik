@echo off
setlocal
pushd "%~dp0.." || exit /b 1
uv run ruff check .
if errorlevel 1 goto failed
uv run ruff format --check .
if errorlevel 1 goto failed
uv run python -m mypy src
if errorlevel 1 goto failed
popd
exit /b 0

:failed
set "check_result=%errorlevel%"
popd
exit /b %check_result%
