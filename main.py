"""Project CLI entry — delegates to the bot package."""

from app.bot.main import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
