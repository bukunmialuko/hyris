from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import quiz

app = FastAPI(title="Hyris API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*"],  # tighten to your extension ID in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quiz.router, prefix="/quiz", tags=["quiz"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
