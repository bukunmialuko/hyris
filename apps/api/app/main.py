import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import deps
from app.routers import attempts, history, quiz
from app.services.persistence import checkpointer_lifespan, engine_lifespan, store_lifespan
from app.services.runs import registry

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
    # The checkpointer is async because the sync PostgresSaver has no async methods and the graph
    # is driven with astream(); the other two are sync context managers entered on the loop.
    async with checkpointer_lifespan() as checkpointer:
        with store_lifespan() as store, engine_lifespan() as sessions:
            # Two holders on purpose: the router's copies build the graph, deps' copies serve
            # request-time dependencies. Both are set here, once, from the same objects.
            quiz.set_store(store)
            quiz.set_sessions(sessions)
            quiz.set_checkpointer(checkpointer)
            deps.set_store(store)
            deps.set_sessions(sessions)
            try:
                yield
            finally:
                # Before the backends close: a run still writing its quiz row needs them open.
                await registry.drain()


app = FastAPI(title="Hyris API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Starlette matches allow_origins exactly, so extension origins need the regex form.
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quiz.router, prefix="/quiz", tags=["quiz"])
app.include_router(history.router, prefix="/quizzes", tags=["quizzes"])
app.include_router(attempts.router, prefix="/attempts", tags=["attempts"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
