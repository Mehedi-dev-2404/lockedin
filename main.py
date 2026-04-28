import asyncio
import logging
import uvicorn
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from config.settings import TELEGRAM_BOT_TOKEN
from bot.handlers.onboarding_handler import build_onboarding_handler
from bot.handlers.command_handler import streak_command, profile_command, help_command, reset_onboarding_command
from bot.handlers.checkin_handler import checkin_command
from bot.handlers.message_handler import handle_message
from bot.scheduler.daily_checkin import schedule_daily_nudges
from api.main import app as fastapi_app

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting Koda...")

    tg_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    tg_app.add_handler(build_onboarding_handler())
    tg_app.add_handler(CommandHandler("streak", streak_command))
    tg_app.add_handler(CommandHandler("profile", profile_command))
    tg_app.add_handler(CommandHandler("checkin", checkin_command))
    tg_app.add_handler(CommandHandler("help", help_command))
    tg_app.add_handler(CommandHandler("resetonboarding", reset_onboarding_command))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    schedule_daily_nudges(tg_app)

    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    logger.info("Koda is live.")

    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling()
        try:
            await server.serve()
        finally:
            await tg_app.updater.stop()
            await tg_app.stop()


if __name__ == "__main__":
    asyncio.run(main())
