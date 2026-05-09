from __future__ import annotations

import uvicorn

from src.api.app import create_app
from src.core.settings import load_settings


def main() -> None:
    settings = load_settings()
    print(f"HORIZON_API_READY http://{settings.host}:{settings.port}", flush=True)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
