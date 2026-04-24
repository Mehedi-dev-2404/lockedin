import logging
from telegram.ext import ApplicationBuilder
from config.settings import TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Koda...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    logger.info("Koda is live.")
    app.run_polling()

if __name__ == "__main__":
    main()