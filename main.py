
import hashlib
import hmac
import json
import logging
import os
import time

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


# ---------- Configuration ----------

BASE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"

# Create the folder now; we will add the Mini App files later.
WEBAPP_DIR.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "").strip().rstrip("/")

MAX_INITDATA_AGE = int(
    os.getenv("TELEGRAM_INITDATA_MAX_AGE", "86400")
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("devpocket")


# ---------- Telegram bot ----------

telegram_app = None


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    if MINI_APP_URL.startswith("https://"):
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🚀 Открыть DevPocket",
                        web_app=WebAppInfo(url=MINI_APP_URL),
                    )
                ]
            ]
        )

        await update.effective_message.reply_text(
            "👋 Добро пожаловать в DevPocket!\n\n"
            "Твоя среда разработчика внутри Telegram.\n"
            "Открой приложение кнопкой ниже.",
            reply_markup=keyboard,
        )
    else:
        await update.effective_message.reply_text(
            "👋 Добро пожаловать в DevPocket!\n\n"
            "Бот запущен, но Mini App ещё не подключён.\n"
            "Сначала развернём сайт и настроим MINI_APP_URL."
        )


# ---------- Telegram Mini App verification ----------

def verify_init_data(init_data: str) -> dict:
    """Verify Telegram Web App initData using the bot token."""

    if not BOT_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Telegram bot is not configured",
        )

    if not init_data or len(init_data) > 16384:
        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram initData",
        )

    try:
        pairs = parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=True,
        )

        # Duplicate fields are rejected to avoid ambiguous validation.
        if len(dict(pairs)) != len(pairs):
            raise ValueError("Duplicate fields")

        data = dict(pairs)
        received_hash = data.pop("hash", "")

        if len(received_hash) != 64:
            raise ValueError("Invalid hash")

        auth_date = int(data.get("auth_date", "0"))
        now = int(time.time())

        if auth_date <= 0:
            raise ValueError("Missing auth_date")

        if auth_date > now + 60:
            raise ValueError("Future auth_date")

        if now - auth_date > MAX_INITDATA_AGE:
            raise ValueError("Expired initData")

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            raise ValueError("Hash mismatch")

        user_json = data.get("user")
        if not user_json:
            raise ValueError("Missing user")

        user = json.loads(user_json)

        if not isinstance(user, dict) or not user.get("id"):
            raise ValueError("Invalid user")

        # Return only fields needed by the application.
        return {
            "id": user["id"],
            "first_name": user.get("first_name", ""),
            "username": user.get("username"),
            "language_code": user.get("language_code"),
        }

    except HTTPException:
        raise
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=401,
            detail="Telegram verification failed",
        )


# ---------- Application lifecycle ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    if BOT_TOKEN:
        telegram_app = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )

        telegram_app.add_handler(
            CommandHandler("start", start_command)
        )

        await telegram_app.initialize()
        await telegram_app.start()

        if telegram_app.updater:
            await telegram_app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES
            )

        logger.info("Telegram bot started")
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN is missing; bot polling is disabled"
        )

    logger.info("DevPocket API started")

    try:
        yield
    finally:
        if telegram_app:
            if telegram_app.updater and telegram_app.updater.running:
                await telegram_app.updater.stop()

            if telegram_app.running:
                await telegram_app.stop()

            await telegram_app.shutdown()

            logger.info("Telegram bot stopped")


# ---------- FastAPI ----------

app = FastAPI(
    title="DevPocket API",
    description="Developer workspace inside Telegram",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=str(WEBAPP_DIR)),
    name="static",
)


@app.get("/", include_in_schema=False)
async def home():
    index_file = WEBAPP_DIR / "index.html"

    if index_file.is_file():
        return FileResponse(index_file)

    return JSONResponse(
        {
            "name": "DevPocket",
            "status": "starting",
            "message": "Mini App interface will be added next.",
        }
    )


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "DevPocket",
        "version": "0.1.0",
    }


@app.get("/api/status")
async def api_status():
    return {
        "service": "DevPocket",
        "api": "online",
        "bot_configured": bool(BOT_TOKEN),
        "mini_app_configured": MINI_APP_URL.startswith("https://"),
    }


@app.post("/api/me")
async def get_current_user(request: Request):
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400,
            detail="Request body must be valid JSON",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail="Request body must be a JSON object",
        )

    init_data = body.get("initData")

    if not isinstance(init_data, str):
        raise HTTPException(
            status_code=400,
            detail="initData is required",
        )

    user = verify_init_data(init_data)

    return {
        "ok": True,
        "user": user,
    }
