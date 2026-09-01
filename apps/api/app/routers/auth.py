"""Device registration: the one endpoint that hands out an identity."""

from fastapi import APIRouter, HTTPException

from app.schemas.quiz import DeviceToken
from app.services.auth import AuthUnavailable, mint_token, new_user_id

router = APIRouter()


@router.post("/device", response_model=DeviceToken, status_code=201)
def register_device() -> DeviceToken:
    """Mint a fresh identity and a token proving it.

    Unauthenticated on purpose -- there is nothing to authenticate yet. What it buys over the old
    X-User-Id header is that the caller cannot *choose* the id, so it cannot name someone else's.
    """
    try:
        user_id = new_user_id()
        return DeviceToken(user_id=user_id, token=mint_token(user_id))
    except AuthUnavailable as e:
        raise HTTPException(503, str(e)) from e
