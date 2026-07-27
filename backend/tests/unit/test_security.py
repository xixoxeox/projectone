import uuid

from screener.config import Settings
from screener.modules.identity.application.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_access_token() -> None:
    hashed = hash_password("a sufficiently strong password")
    assert verify_password("a sufficiently strong password", hashed)
    settings = Settings(app_env="test")
    user_id = uuid.uuid4()
    token, ttl = create_access_token(user_id, "admin", settings)
    assert decode_access_token(token, settings)["sub"] == str(user_id)
    assert ttl == settings.jwt_access_ttl_seconds
