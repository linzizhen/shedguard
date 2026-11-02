"""本地启动入口：python -m shedguard_server。"""

from __future__ import annotations

import uvicorn

from shedguard_server.app import create_app
from shedguard_server.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()