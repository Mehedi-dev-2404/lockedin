import logging
import stripe
from fastapi import APIRouter, HTTPException, Request
from telegram import Bot
from config.settings import STRIPE_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN
from db.queries.user_queries import get_user_by_username, update_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # Extract Telegram username from custom fields
        telegram_username = None
        for field in session.get("custom_fields", []):
            if field.get("key") in ("telegramusername", "telegram_username"):
                telegram_username = (field.get("text") or {}).get("value")
                break

        if not telegram_username:
            logger.warning(f"No telegram_username in custom_fields for session {session.get('id')}")
            return {"status": "ok"}

        # Strip leading @ if present
        telegram_username = telegram_username.lstrip("@")

        user = get_user_by_username(telegram_username)
        if not user:
            logger.warning(f"No user found for telegram username: {telegram_username}")
            return {"status": "ok"}

        telegram_id = user["telegram_id"]
        update_user(telegram_id, is_premium=True)
        logger.info(f"Activated premium for {telegram_id} (@{telegram_username})")

        first_name = (user.get("full_name") or telegram_username).split()[0]
        message = (
            f"yo {first_name} \U0001f525 you're locked in. premium activated.\n"
            "Koda's got you from here. let's get that offer."
        )

        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            await bot.send_message(chat_id=telegram_id, text=message)
        except Exception as e:
            logger.error(f"Failed to send premium activation message to {telegram_id}: {e}")

    return {"status": "ok"}
