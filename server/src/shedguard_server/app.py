"""应用装配：配置、日志、中间件、异常处理与路由注册。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from shedguard_server import __version__
from shedguard_server.api.ratelimit import EXEMPT_PATHS, TokenBucketLimiter, client_key
from shedguard_server.api.routes import (
    alerts,
    analysis,
    devices,
    events,
    health,
    images,
    knowledge,
    pets,
    risk,
    series,
    shedding,
    users,
)
from shedguard_server.config import Settings
from shedguard_server.domain.detection import Detector, NullDetector
from shedguard_server.domain.push import PushGateway
from shedguard_server.domain.shedding import StateClassifier
from shedguard_server.errors import (
    ApiError,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    RateLimitedError,
    error_payload,
)
from shedguard_server.ids import new_request_id
from shedguard_server.infra.classifier import OnnxStateClassifier
from shedguard_server.infra.db import create_db_engine, create_session_factory
from shedguard_server.infra.detector import OnnxDetector
from shedguard_server.infra.migrate import run_migrations
from shedguard_server.infra.push import ExpoPushGateway, SkippedPushGateway
from shedguard_server.infra.storage import LocalStorage
from shedguard_server.logging_setup import configure_logging, request_id_var
from shedguard_server.services.health import scan_once
from shedguard_server.services.retention import purge_once

logger = logging.getLogger("shedguard.http")

REQUEST_ID_HEADER = "X-Request-Id"
RETENTION_INTERVAL_SECONDS = 6 * 60 * 60


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


def _build_classifier(
    settings: Settings,
) -> tuple[StateClassifier | None, Exception | None]:
    """加载蜕皮状态分类模型；未配置时返回 None，接口据此返回 503。"""
    if not settings.state_model:
        return None, None
    try:
        classifier = OnnxStateClassifier.from_path(Path(settings.state_model))
    except Exception as exc:  # 加载失败降级而不是崩服务
        logger.exception("状态分类模型加载失败，蜕皮状态接口将不可用")
        return None, exc
    logger.info("已加载状态分类模型 %s", classifier.name)
    return classifier, None


def _build_push_gateway(settings: Settings) -> PushGateway:
    """推送关闭时用占位网关，避免测试与离线环境发起真实网络请求。"""
    if not settings.push_enabled:
        return SkippedPushGateway()
    return ExpoPushGateway(settings.expo_push_url, timeout=settings.push_timeout_seconds)


async def _health_loop(
    session_factory: sessionmaker[Session], settings: Settings, gateway: PushGateway
) -> None:
    """周期扫描设备健康；异常只记日志，不让后台任务退出。"""
    interval = settings.health_scan_minutes * 60
    while True:
        try:
            await asyncio.to_thread(
                scan_once,
                session_factory=session_factory,
                settings=settings,
                gateway=gateway,
            )
        except Exception:  # 后台任务必须自愈
            logger.exception("设备健康扫描失败")
        await asyncio.sleep(interval)


async def _retention_loop(
    session_factory: sessionmaker[Session], settings: Settings, storage: LocalStorage
) -> None:
    """周期清理过期照片；异常只记日志，不让后台任务退出。"""
    while True:
        try:
            await asyncio.to_thread(
                purge_once,
                session_factory=session_factory,
                settings=settings,
                storage=storage,
            )
        except Exception:  # 后台任务必须自愈
            logger.exception("过期照片清理失败")
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)


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
        health_task: asyncio.Task[None] | None = None
        if settings.health_monitor_enabled:
            health_task = asyncio.create_task(
                _health_loop(instance.state.session_factory, settings, instance.state.push_gateway)
            )
            instance.state.health_task = health_task
        retention_task: asyncio.Task[None] | None = None
        if settings.image_retention_days > 0:
            retention_task = asyncio.create_task(
                _retention_loop(
                    instance.state.session_factory,
                    settings,
                    LocalStorage(settings.data_dir),
                )
            )
        instance.state.retention_task = retention_task
        try:
            yield
        finally:
            if health_task is not None:
                health_task.cancel()
                with suppress(asyncio.CancelledError):
                    await health_task
            if retention_task is not None:
                retention_task.cancel()
                with suppress(asyncio.CancelledError):
                    await retention_task
            logger.info("服务停止")

    app = FastAPI(title="shedguard-server", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.resolved_db_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.detector, app.state.detector_error = _build_detector(settings)
    app.state.state_classifier, app.state.classifier_error = _build_classifier(settings)
    app.state.push_gateway = _build_push_gateway(settings)
    rate_limiter = (
        TokenBucketLimiter(
            per_minute=settings.rate_limit_per_minute,
            burst=settings.rate_limit_burst,
        )
        if settings.rate_limit_per_minute > 0
        else None
    )
    app.state.rate_limiter = rate_limiter

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

    @app.middleware("http")
    async def rate_limit(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if (
            rate_limiter is not None
            and path not in EXEMPT_PATHS
            and not path.startswith("/docs/")
            and not rate_limiter.allow(client_key(request))
        ):
            return _error_response(RateLimitedError("请求过于频繁，请稍后再试"))
        return await call_next(request)

    # Starlette 后注册的中间件在外层：先注册限流、再注册上下文，request_context
    # 才会先执行，429 响应也能带上 request_id 与 X-Request-Id。
    app.middleware("http")(request_context)

    # 网页版（React Native Web）调试时需要跨域访问本服务；默认关闭。
    cors_origins = settings.cors_origin_list
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[REQUEST_ID_HEADER],
        )

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
    app.include_router(shedding.router)
    app.include_router(shedding.series_router)
    app.include_router(pets.router)
    app.include_router(knowledge.router)
    app.include_router(risk.router)
    app.include_router(devices.router)
    app.include_router(alerts.router)
    app.include_router(users.router)
    return app