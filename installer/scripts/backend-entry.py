"""PyInstaller entry point for the BioDize FastAPI backend.

This file is frozen by PyInstaller into a standalone executable.
It must NOT be run directly — use the installer build pipeline.

Runtime env vars consumed here:
  PORT         — TCP port  (default 48721)
  HOST         — bind host (default 127.0.0.1)
  LOG_LEVEL    — uvicorn log level (default warning)
"""
from __future__ import annotations

import multiprocessing
import os
import sys

# Required for PyInstaller's onedir mode on Windows.
multiprocessing.freeze_support()


def main() -> None:
    import uvicorn
    # Import the ASGI app object directly so uvicorn works correctly inside
    # a frozen executable (string-based 'app.main:app' import fails in _MEIPASS).
    from app.main import app as asgi_app  # noqa: PLC0415

    port      = int(os.environ.get("PORT",      "48721"))
    host      = os.environ.get("HOST",           "127.0.0.1")
    log_level = os.environ.get("LOG_LEVEL",       "warning")

    uvicorn.run(
        asgi_app,
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
