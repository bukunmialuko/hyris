import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import quiz
from app.services.persistence import store_lifespan

# uvicorn configures only the uvicorn* loggers and leaves root at WARNING with no handler, so app.*
# records would vanish — including the line saying persistence is live. Scoped to this app's tree on
# purpose: logging.basicConfig would set the ROOT level to INFO, which also switches on httpx's
# per-request logging (langchain-openai) in the server and in pytest.
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
if not _app_logger.handlers:
    _app_logger.addHandler(_handler)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Open learner memory once per process and hand it to the router.

    A sync context manager entered on the event loop: connecting and running migrations is blocking
    I/O, but uvicorn serves nothing until this yields, so there is no loop to starve. The router gets
    a store, not a compiled graph, so "importing the app never needs an API key" survives.
    """
    with store_lifespan() as store:
        quiz.set_store(store)
        yield


app = FastAPI(title="Hyris API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Starlette matches allow_origins exactly, so extension origins need the regex form.
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quiz.router, prefix="/quiz", tags=["quiz"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
