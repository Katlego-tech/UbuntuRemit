"""FastAPI application factory for UbuntuRemit Gateway."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ubunturemit_gateway.dependencies import GatewayDependencies
from ubunturemit_gateway.routes.compliance import router as compliance_router
from ubunturemit_gateway.routes.quotes import router as quotes_router
from ubunturemit_gateway.routes.transfers import router as transfers_router


def create_app(dependencies: GatewayDependencies | None = None) -> FastAPI:
    """Build the app around its external sources.

    With none given, every endpoint that needs one answers 503 -- see dependencies.py.
    """
    app = FastAPI(
        title="UbuntuRemit Gateway API",
        version="1.0.0",
        description="FastAPI gateway for ISO 20022 cross-border payments & ASCO orchestration.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.dependencies = dependencies or GatewayDependencies()

    app.include_router(quotes_router)
    app.include_router(transfers_router)
    app.include_router(compliance_router)

    @app.get("/healthz")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "ubunturemit-gateway"}

    return app


app = create_app()
