import logging
import stripe
from fastapi import APIRouter, HTTPException, Request
from telegram import Bot
from config.settings import STRIPE_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN
from db.queries.user_queries import get_user_by_payment_code, update_user

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

        # Extract activation code from custom fields
        activation_code = None
        custom_fields = session.custom_fields or []
        for field in custom_fields:
            if field.key in ("activationcode", "activation_code"):
                activation_code = field.text.value if field.text else None
                break

        if not activation_code:
            logger.warning(f"No activation code in custom_fields for session {session.id}")
            return {"status": "ok"}

        activation_code = activation_code.strip().upper()

        user = get_user_by_payment_code(activation_code)
        if not user:
            logger.warning(f"No user found for activation code: {activation_code}")
            return {"status": "ok"}

        telegram_id = user["telegram_id"]
        update_user(telegram_id, is_premium=True)
        logger.info(f"Activated premium for {telegram_id} (code: {activation_code})")

        first_name = (user.get("full_name") or "there").split()[0]
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
