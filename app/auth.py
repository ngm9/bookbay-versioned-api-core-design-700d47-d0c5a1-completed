import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/oauth/token")
JWT_SECRET = os.getenv("JWT_SECRET", "local-bookbay-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "bookbay-mobile")


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    role: str


def decode_access_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> AuthUser:
    claims = decode_access_token(token)
    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise HTTPException(status_code=401, detail="Token subject is missing")
    user = db.get(User, subject)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="User account is unavailable")
    return AuthUser(id=user.id, email=user.email, role=user.role)
