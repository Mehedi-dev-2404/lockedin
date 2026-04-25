import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from config.settings import TELEGRAM_BOT_TOKEN
from bot.handlers.onboarding_handler import build_onboarding_handler
from bot.handlers.command_handler import streak_command, profile_command, help_command
from bot.handlers.checkin_handler import checkin_command
from bot.handlers.message_handler import handle_message
from bot.scheduler.daily_checkin import schedule_daily_nudge

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Koda...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(build_onboarding_handler())
    app.add_handler(CommandHandler("streak", streak_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    schedule_daily_nudge(app)

    logger.info("Koda is live.")
    app.run_polling()


if __name__ == "__main__":
    main()
