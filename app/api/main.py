from __future__ import annotations

from pathlib import Path as FilePath

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import chat_routes, v1_routes, web_routes
from app.middleware.cloudflare_access import CloudflareAccessMiddleware

BASE_DIR = FilePath(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"

EXPECTED_ROUTE_INVENTORY = {
    ("GET", "/"),
    ("GET", "/search"),
    ("GET", "/browse"),
    ("GET", "/browse/datasets/{dataset_id}"),
    ("GET", "/api"),
    ("GET", "/series/{dataset_id}/{indicator_code}"),
    ("GET", "/health"),
    ("GET", "/health/db"),
    ("GET", "/v1/datasets"),
    ("GET", "/v1/datasets/{dataset_id}"),
    ("GET", "/v1/datasets/{dataset_id}/series"),
    ("GET", "/v1/series/search"),
    ("GET", "/v1/series/search/semantic"),
    ("GET", "/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}"),
    (
        "GET",
        "/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations",
    ),
    (
        "GET",
        "/v1/datasets/{dataset_id}/series/by-indicator/{indicator_code}/observations.csv",
    ),
    ("GET", "/chat"),
    ("POST", "/v1/chat/retrieve"),
    ("POST", "/v1/chat/ask"),
}


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stats Finder API",
        description=(
            "A lightweight API for discovering official statistical series "
            "grounded in published SDMX data."
        ),
        version="0.1.0",
    )

    app.add_middleware(CloudflareAccessMiddleware)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(web_routes.router)
    app.include_router(v1_routes.router)
    app.include_router(chat_routes.router)
    assert_expected_routes_registered(app)

    return app


def get_route_inventory(app: FastAPI) -> set[tuple[str, str]]:
    inventory: set[tuple[str, str]] = set()

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)

        if path is None or methods is None:
            continue

        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue

            inventory.add((method, path))

    return inventory


def assert_expected_routes_registered(app: FastAPI) -> None:
    registered_routes = get_route_inventory(app)
    missing_routes = EXPECTED_ROUTE_INVENTORY - registered_routes

    if missing_routes:
        formatted_routes = ", ".join(
            f"{method} {path}" for method, path in sorted(missing_routes)
        )
        raise RuntimeError(f"Expected routes are not registered: {formatted_routes}")


app = create_app()
