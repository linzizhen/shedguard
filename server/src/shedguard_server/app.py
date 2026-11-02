"""应用装配：配置、日志、中间件、异常处理与路由注册。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shedguard_server import __version__
from shedguard_server.api.routes import analysis, events, health, images, series
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detector, NullDetector
from shedguard_server.errors import (
    ApiError,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    error_payload,
)
from shedguard_server.ids import new_request_id
from shedguard_server.infra.db import create_db_engine, create_session_factory
from shedguard_server.infra.detector import OnnxDetector
from shedguard_server.infra.migrate import run_migrations
from shedguard_server.logging_setup import configure_logging, request_id_var

logger = logging.getLogger("shedguard.http")

REQUEST_ID_HEADER = "X-Request-Id"


def _error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=error_payload(error, request_id_var.get()),
    )


def _build_detector(settings: Settings) -> tuple[Detector, Exception | None]:
    """加载检测模型；失败时回退到整图框，并记下原因供 `/readyz` 报告。"""
    if not settings.detector_model:
        return NullDetector(), None
    try:
        detector = OnnxDetector.from_path(
            Path(settings.detector_model),
            min_confidence=settings.detect_min_confidence,
        )
    except Exception as exc:  # 任何加载失败都应降级而不是崩服务
        logger.exception("检测模型加载失败，回退到 NullDetector")
        return NullDetector(), exc
    logger.info("已加载检测模型 %s", detector.name)
    return detector, None


def create_app(settings: Settings | None = None, *, create_data_dir: bool = True) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_format, settings.tzinfo)

    @asynccontextmanager
    async def lifespan(instance: FastAPI) -> AsyncIterator[None]:
        if create_data_dir:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
        instance.state.migration_error = None
        try:
            run_migrations(settings.resolved_db_url)
        except Exception as exc:
            instance.state.migration_error = exc
            logger.exception("数据库迁移失败")
        logger.info("服务启动 data_dir=%s", settings.data_dir)
        yield
        logger.info("服务停止")

    app = FastAPI(title="shedguard-server", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.resolved_db_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.detector, app.state.detector_error = _build_detector(settings)

    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    app.middleware("http")(request_context)

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(str(item.get("msg", "")) for item in exc.errors()) or "请求参数不合法"
        return _error_response(InvalidRequestError(detail))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error_response(NotFoundError("资源不存在"))
        return _error_response(InvalidRequestError(str(exc.detail)))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未捕获异常", exc_info=exc)
        return _error_response(InternalError("服务内部错误"))

    app.include_router(health.router)
    app.include_router(images.router)
    app.include_router(series.router)
    app.include_router(events.router)
    app.include_router(analysis.router)
    return app