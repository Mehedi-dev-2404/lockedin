import logging
import anthropic
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS
from bot.koda.personality import build_system_prompt
from db.queries.message_queries import save_message, get_recent_messages

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def get_koda_response(telegram_id: int, user_message: str, user_context: dict) -> str:
    system_prompt = build_system_prompt(user_context)
    history = get_recent_messages(telegram_id, limit=20)
    messages = history + [{"role": "user", "content": user_message}]

    try:
        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        response_text = message.content[0].text
        save_message(telegram_id, "user", user_message)
        save_message(telegram_id, "assistant", response_text)
        return response_text
    except anthropic.APIConnectionError as e:
        logger.error(f"Anthropic connection error for user {telegram_id}: {e}")
        return "I'm having trouble connecting right now. Try again in a minute."
    except anthropic.RateLimitError as e:
        logger.warning(f"Anthropic rate limit hit for user {telegram_id}: {e}")
        return "I'm getting a lot of messages right now. Give me a few seconds and try again."
    except anthropic.APIStatusError as e:
        logger.error(f"Anthropic API error for user {telegram_id}: status={e.status_code} body={e.body}")
        return "Something went wrong on my end. Try again shortly."
    except Exception as e:
        logger.exception(f"Unexpected error in get_koda_response for user {telegram_id}: {e}")
        return "Something unexpected happened. Try again."
