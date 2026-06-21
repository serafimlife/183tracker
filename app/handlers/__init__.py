"""Handler routers — thin Telegram layer; delegate to services."""

from aiogram import Router

from app.handlers import (
    export_command,
    help,
    history_command,
    import_command,
    in_command,
    log_command,
    onboarding,
    out_command,
    report,
    settings,
    start,
    stay_callbacks,
    where_command,
)

root_router = Router(name="root")

root_router.include_router(start.router)
root_router.include_router(help.router)
root_router.include_router(onboarding.router)
root_router.include_router(in_command.router)
root_router.include_router(out_command.router)
root_router.include_router(log_command.router)
root_router.include_router(where_command.router)
root_router.include_router(history_command.router)
root_router.include_router(report.router)
root_router.include_router(stay_callbacks.router)
root_router.include_router(export_command.router)
root_router.include_router(import_command.router)
root_router.include_router(settings.router)
