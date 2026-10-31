"""FastAPI application entrypoint: uvicorn app.main:app --reload"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .observability import configure_tracing, record, span


def create_app() -> FastAPI:
    settings = get_settings()
    configure_tracing(settings)
    app = FastAPI(
        title="SYNAPSE",
        description="Intelligent AI Workflow Compiler & Execution Runtime",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        """One span per request, so a node span always has a parent to hang
        off and a whole run shows up in Langfuse as a single trace."""
        route = request.url.path
        with span(
            f"{request.method} {route}",
            **{"http.method": request.method, "http.route": route},
        ) as active:
            response = await call_next(request)
            record(active, **{"http.status_code": response.status_code})
            return response

    app.include_router(router)
    return app


app = create_app()
