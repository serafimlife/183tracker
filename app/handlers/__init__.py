"""Handler routers — thin Telegram layer; delegate to services."""

from aiogram import Router

from app.handlers import in_command, onboarding, out_command, start, stay_callbacks

root_router = Router(name="root")

root_router.include_router(start.router)
root_router.include_router(onboarding.router)
root_router.include_router(in_command.router)
root_router.include_router(out_command.router)
root_router.include_router(stay_callbacks.router)
