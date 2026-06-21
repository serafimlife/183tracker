#!/bin/sh
set -e

echo "Initialising database schema…"
uv run python -c "
import asyncio
from app.database.session import init_db, create_tables
from app.bot.config import get_settings

async def setup():
    settings = get_settings()
    await init_db(settings.database_url)
    await create_tables()

asyncio.run(setup())
"

echo "Starting bot…"
exec uv run bot
