from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import quiz

app = FastAPI(title="Hyris API", version="0.2.0")

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
