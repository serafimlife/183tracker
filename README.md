# 183Tracker — Tax Residency Tracker Bot

A Telegram bot for digital nomads and expats to track physical presence across countries, monitor 183-day tax residency thresholds, and stay on top of the Schengen Area 90/180-day rule.

---

## Features

- **Travel logging** — record country entries and exits with `/in` and `/out`
- **Calendar-year tracking** — days spent per country in the current or any past calendar year
- **Rolling 365-day tracking** — a moving 12-month window, for countries that use a rolling test rather than a calendar year
- **Schengen 90/180 tracking** — combined days across all 29 Schengen member states against the 90-days-in-any-180-days rule, with a "next available entry" date when you're at the limit
- **Threshold alerts** — colour-coded indicators (🟢 🟡 🔴) as you approach the 183-day and 90-day caps
- **Travel history** — paginated history with country and date filters; edit or remove individual stays
- **Import / export** — bring in historical stays from CSV or XLSX; export your full history at any time
- **Multi-language** — English, Spanish, French, German, Russian, Japanese, Korean, Chinese
- **Privacy-first** — no account required; data is tied only to your Telegram user ID

---

## Screenshots

_Screenshots to be added._

---

## Prerequisites

Before you start you will need:

- A Linux server or VPS (Ubuntu 22.04 or later recommended)
- [Docker](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on that server
- A Telegram account (to create the bot via @BotFather)
- `git` installed on the server (`sudo apt install git`)

Two deployment paths are available. **Full Docker** (steps 5 → 7 below) runs both the bot and the database as containers — the easiest path for new deployments. **Manual** runs the bot directly on the host with Python/uv and uses Docker only for PostgreSQL — useful if you prefer systemd management or already have Python installed.

---

## Deployment guide

### 1. Create a Telegram bot and get a token

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`.
3. When prompted, choose a display name (e.g. `My Residency Tracker`).
4. When prompted, choose a username — it must end in `bot` (e.g. `myresidency_bot`).
5. BotFather will reply with a token that looks like `123456789:AABBCCddEEff...`. **Copy this — you will need it in step 4.**

### 2. Get the code

SSH into your server and clone the repository:

```bash
git clone <your-repo-url>
cd 183days_rule_bot
```

### 3. Install uv and Python 3.12 *(manual deployment only)*

Skip this step if you are using the full Docker path.

[uv](https://github.com/astral-sh/uv) is the dependency manager used by this project.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env          # add uv to PATH for this session
uv python install 3.12
```

Install project dependencies:

```bash
uv sync
```

### 4. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
nano .env          # or any editor you prefer
```

The variables are:

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | Yes | The token from @BotFather (step 1) |
| `POSTGRES_USER` | Yes (Docker) | PostgreSQL username. Default: `botuser` |
| `POSTGRES_PASSWORD` | Yes (Docker) | PostgreSQL password. Generate a strong one: `openssl rand -base64 32` |
| `POSTGRES_DB` | Yes (Docker) | Database name. Default: `183days_bot` |
| `DATABASE_URL` | Yes (manual) | PostgreSQL connection string — see below |
| `ALLOWED_USER_IDS` | No | Comma-separated Telegram user IDs that may use the bot. **Leave empty for a public bot** — any Telegram user will be allowed. Set this only for a private/personal instance (e.g. `123456789,987654321`). Get your ID from [@userinfobot](https://t.me/userinfobot). |
| `LOG_LEVEL` | No | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Defaults to `INFO` |
| `REDIS_URL` | No | Redis connection string (e.g. `redis://localhost:6379/0`). Required only for multi-instance deployments or if you need FSM state to survive bot restarts. Without it, conversation state is held in memory and lost on restart |

**Full Docker path:** `DATABASE_URL` is built automatically by `docker-compose.yml` from the `POSTGRES_*` variables — you do not need to set it manually. Just fill in `POSTGRES_PASSWORD` with a strong value.

**Manual/systemd path:** Set `DATABASE_URL` directly using the `asyncpg` driver format:

```
DATABASE_URL=postgresql+asyncpg://botuser:yourpassword@localhost:5432/183days_bot
```

**Keep `.env` private** — it contains your bot token and database password. Never commit it to version control.

### 5. Start the services

#### Full Docker (bot + database)

```bash
docker compose up -d
```

This builds the bot image and starts both the bot and the database. The bot container waits for PostgreSQL to be healthy, then initialises the schema automatically, then starts polling. Check the logs:

```bash
docker compose logs -f bot
```

You should see a line like `Bot started as @yourbot_name`. If you see that, skip to step 8.

#### Manual (database only)

If you are running the bot directly on the host, start only the database:

```bash
docker compose up -d postgres
```

Verify it started:

```bash
docker compose ps
```

You should see `183days_bot_db` with status `healthy`.

### 6. Initialise the database schema *(manual deployment only)*

Skip this step if you started the full Docker stack in step 5 — the Docker entrypoint (`docker/entrypoint.sh`) runs schema initialisation automatically before the bot process starts. If you run the bot directly with `uv run bot` or via systemd **without** Docker, you must run this step manually or you will get `UndefinedTableError: relation "users" does not exist` on startup.

Run this once after the database is healthy:

```bash
uv run python -c "
import asyncio
from app.database.session import init_db, create_tables
from app.bot.config import get_settings

async def setup():
    await init_db(get_settings().database_url)
    await create_tables()

asyncio.run(setup())
"
```

You should see no errors. This only needs to be run once (or after adding new models in a future version).

> **Note:** Alembic migration files are not yet included in this repository. The command above uses SQLAlchemy's `create_all` to build the schema from the current models — suitable for new deployments. Future versions will add proper Alembic migrations for schema upgrades.

### 7. Start the bot *(manual deployment only)*

Skip this step if you started the full Docker stack in step 5.

You can run the bot directly for a quick test:

```bash
uv run bot
```

You should see a log line like:

```
INFO  Bot started as @yourbot_name (id=123456789)
```

Press `Ctrl+C` to stop.

**For production** — use systemd to keep the bot running and restart it automatically after reboots or crashes.

Create a service file:

```bash
sudo nano /etc/systemd/system/183days-bot.service
```

Paste the following, replacing `/home/youruser/183days_rule_bot` with the actual path to the cloned project and `youruser` with your Linux username:

```ini
[Unit]
Description=183days rule bot
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/183days_rule_bot
ExecStart=/home/youruser/.local/bin/uv run bot
Restart=on-failure
RestartSec=5
EnvironmentFile=/home/youruser/183days_rule_bot/.env

[Install]
WantedBy=multi-user.target
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable 183days-bot
sudo systemctl start 183days-bot
```

Check the status:

```bash
sudo systemctl status 183days-bot
sudo journalctl -u 183days-bot -f    # follow live logs
```

### 8. Confirm it is working

Open Telegram, find your bot by its username, and send `/start`. You should receive the welcome message with a date format prompt. If you do, the bot is running and connected to the database.

---

## Updating / redeploying

#### Full Docker

```bash
git pull
docker compose build --pull          # rebuild the bot image with updated code
docker compose up -d                 # recreate changed containers; schema init runs automatically
```

> **Warning:** Never run `docker compose down -v` in production — the `-v` flag deletes all named volumes, including `postgres_data`, which contains your entire database. Use `docker compose down` (no flags) to stop containers while keeping data safe.

#### Manual (systemd)

```bash
git pull
uv sync                              # install any new dependencies
sudo systemctl restart 183days-bot
```

If a new version adds database columns, re-run the schema initialisation command from step 6 (it only creates missing tables and does not delete data). Once Alembic migrations are in place, updates will use `alembic upgrade head` instead.

---

## Protecting your data

All user travel data lives in the `postgres_data` Docker named volume (or on the host filesystem if you are using a self-managed PostgreSQL install). A few commands can permanently delete it — know the difference before you run them.

### Safe Docker commands

| Command | Effect on data |
|---|---|
| `docker compose down` | Stops and removes containers. **Volume is kept.** |
| `docker compose stop` | Stops containers without removing them. **Volume is kept.** |
| `docker compose restart` | Restarts containers. **Volume is kept.** |
| `docker compose up -d` | Starts/recreates containers. **Volume is kept.** |

### Dangerous commands — will delete all data

| Command | Effect on data |
|---|---|
| `docker compose down -v` | Removes containers **and all named volumes** — database is gone. |
| `docker volume rm postgres_data` | Deletes the volume directly — database is gone. |
| `docker volume prune` | Removes all unused volumes — may delete the database if the container is stopped. |

Never run any of the dangerous commands on a production deployment unless you intend to wipe the database and start fresh.

### Backups

Take a backup before updates or any Docker maintenance (substitute your `POSTGRES_USER` and `POSTGRES_DB` values if you changed the defaults):

```bash
docker exec 183days_bot_db pg_dump -U botuser 183days_bot > backup_$(date +%Y%m%d).sql
```

Restore from a backup:

```bash
cat backup_20240101.sql | docker exec -i 183days_bot_db psql -U botuser -d 183days_bot
```

Store backups outside the server (e.g. copy them to your local machine with `scp`) so they survive a VPS failure.

---

## Security hardening

The following security measures are built into the provided configuration.

### PostgreSQL is not exposed to the internet

`docker-compose.yml` does **not** publish the PostgreSQL port to the host. The database is reachable only from inside the Docker Compose network (i.e. by the bot container). No external TCP access to port 5432 is possible. This is the single most important control — a publicly exposed PostgreSQL with weak credentials is the most common cause of database compromise.

### Strong, randomised database credentials

The template uses `POSTGRES_USER=botuser` (not the default superuser `postgres`) and requires you to generate a strong password with `openssl rand -base64 32`. The password lives only in `.env` and is never hardcoded in any source file.

### Access control with `ALLOWED_USER_IDS`

The `ALLOWED_USER_IDS` environment variable is an optional per-user allowlist enforced at the outermost middleware layer (before any database activity). 

- **Leave it empty for a public bot** — all Telegram users can interact with the bot. This is the normal setting for a publicly advertised service.
- **Set it for a private/personal instance** — only the listed Telegram user IDs will receive responses; all others are silently ignored and logged at WARNING level. Get your own Telegram user ID from [@userinfobot](https://t.me/userinfobot).

### Input sanitisation

User-supplied content (display names, CSV import data) is passed through HTML escapers before being included in any bot response, preventing HTML injection via Telegram's Bot API parse mode.

### Pinned Docker base image for `uv`

`Dockerfile` references a specific version tag (`ghcr.io/astral-sh/uv:0.7.13`) rather than `:latest`, so builds are reproducible and a supply-chain compromise of the `:latest` tag cannot silently affect your deployment. To upgrade, bump the version tag in the `FROM` line.

---

## Running tests

The project has a comprehensive test suite covering the residency engine, report service, Schengen calculations, import/export, and more:

```bash
uv run pytest
```

To run a specific file:

```bash
uv run pytest tests/test_schengen.py -v
```

---

## Contributing

Issues and pull requests are welcome. Please open an issue before starting significant work so we can discuss the approach. There is no `CONTRIBUTING.md` yet — basic expectations are: follow the existing code style, add tests for new behaviour, and ensure `uv run pytest` passes before submitting.

---

## License

[PolyForm Noncommercial License 1.0.0](LICENSE.md) — free for personal and non-commercial use.

---

## Disclaimer

This bot estimates physical presence only. It does not provide legal or tax advice. Day counts may differ from those used by tax authorities depending on how "day of presence" is defined under applicable law. Always consult a qualified legal or tax professional regarding your tax obligations. The authors are not responsible for the accuracy of any calculation produced by this software.
