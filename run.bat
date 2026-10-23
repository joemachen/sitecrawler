@echo off
rem Launch the sitecrawler web UI. Double-click, or run from any terminal.
rem Pass a crawl file to open it read-only:  run.bat crawls\example.com-20261022-120000.db

cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed. Install it from https://docs.astral.sh/uv/ and run this again.
    pause
    exit /b 1
)

if not exist ".venv\" (
    echo First run: installing dependencies...
    uv sync
    if errorlevel 1 (
        echo uv sync failed.
        pause
        exit /b 1
    )
)

echo Starting sitecrawler at http://127.0.0.1:8765  (close this window or press Ctrl+C to stop)
uv run sitecrawler serve %*

if errorlevel 1 pause
