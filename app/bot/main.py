import json
import logging
import urllib.request

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def resolve_session_with_api(session_token: str, telegram_id: int, fullname:str, username:str) -> str:
    payload = json.dumps({
        "session_token": session_token,
        "telegram_id": telegram_id,
        "username": username,
        "full_name":fullname,
     
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{settings.API_BASE_URL}/auth/resolve-session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
        return data["code"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id 
    full_name = f"{update.effective_user.first_name} {update.effective_user.last_name}"
    username = f"{update.effective_user.username}"

    
    session_token = context.args[0] if context.args else None
    if not session_token:
        await update.message.reply_text(
            "❌ Сессия не найдена.\n\n"
            "Открой сайт и нажми 'Войти через Telegram', "
            "чтобы получить ссылку."
        )
        return

    try: 
        code = await resolve_session_with_api(session_token, tg_id, full_name, username)
    except Exception:
        logger.exception("Failed to resolve Telegram login session through the API")
        await update.message.reply_text(
            "❌ Сессия не найдена или уже использована.\n\n"
            "Обнови страницу сайта и попробуй снова."
        )
        return

    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"🔐 Твой код подтверждения:\n\n"
        f"<b>{code}</b>\n\n"
        f"⏳ Код действителен 5 минут.\n"
        f"Введи его на сайте.",
        parse_mode="HTML"
    )
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Используй /start чтобы получить код для входа на сайт."
    )

def main():
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    logger.info("Telegram bot is starting")
    main()
