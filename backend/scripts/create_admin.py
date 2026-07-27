"""Create the one administrator account from interactive environment variables."""

import asyncio
import os

from sqlalchemy import select

from screener.modules.identity.application.security import hash_password
from screener.modules.identity.infrastructure.models import User
from screener.shared.database import SessionFactory


async def main() -> None:
    username, password = os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"]
    if len(password) < 12:
        raise ValueError("ADMIN_PASSWORD must contain at least 12 characters")
    async with SessionFactory() as session:
        if await session.scalar(select(User).where(User.username == username)):
            raise ValueError("Administrator already exists")
        session.add(User(username=username, password_hash=hash_password(password), role="admin"))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
