from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dice_detector.api.routes import router
from dice_detector.api.state import AppState
from dice_detector.models import AppConfig


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    state = app.state.app_state
    await state.initialize()
    yield
    await state.shutdown()


def create_app(config: AppConfig | None = None) -> FastAPI:
    app = FastAPI(
        title="Dice Detector API",
        description="Local API for IRL D&D dice detection",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.config = config or AppConfig()
    app.state.app_state = AppState(app.state.config)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app.state.config.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app


app = create_app()
