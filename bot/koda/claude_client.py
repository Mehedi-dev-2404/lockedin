import json
import logging
import anthropic
from config.settings import CLAUDE_MODEL, CLAUDE_MAX_TOKENS
from bot.koda.anthropic_client import anthropic_client
from bot.koda.personality import build_system_prompt
from bot.koda.utils import clean_json, get_display_name
from db.queries.message_queries import save_message, get_recent_messages
from db.queries.user_queries import get_user, update_user

logger = logging.getLogger(__name__)

_INTENT_CLASSIFIER_SYSTEM = """You are an intent classifier. Given a user message, extract any of the following activities if mentioned. Respond ONLY with valid JSON, nothing else.

{
  "leetcode": true/false,
  "leetcode_count": number or null,
  "leetcode_topic": true/false,
  "leetcode_topics": array of strings or null,
  "applied": true/false,
  "company": string or null,
  "role": string or null,
  "project_work": true/false
}

For leetcode_topic: set true when the user says they finished, completed, or are done with a specific topic, section, or problem set — e.g. "done with arrays and hashing", "finished two pointers", "completed sliding window", "done with blind 75 trees section".
For leetcode_topics: list the exact topic names mentioned, normalised to lowercase (e.g. ["arrays and hashing", "two pointers"]). Null if leetcode_topic is false.
For leetcode: set true for any general leetcode activity (solving problems, grinding, etc). A topic completion also counts as leetcode activity.

Examples:
"did 3 leetcode problems" -> {"leetcode": true, "leetcode_count": 3, "leetcode_topic": false, "leetcode_topics": null, "applied": false, "company": null, "role": null, "project_work": false}
"done with arrays and hashing" -> {"leetcode": true, "leetcode_count": null, "leetcode_topic": true, "leetcode_topics": ["arrays and hashing"], "applied": false, "company": null, "role": null, "project_work": false}
"finished two pointers and sliding window" -> {"leetcode": true, "leetcode_count": null, "leetcode_topic": true, "leetcode_topics": ["two pointers", "sliding window"], "applied": false, "company": null, "role": null, "project_work": false}
"completed blind 75 trees section" -> {"leetcode": true, "leetcode_count": null, "leetcode_topic": true, "leetcode_topics": ["trees"], "applied": false, "company": null, "role": null, "project_work": false}
"applied to Google SWE intern" -> {"leetcode": false, "leetcode_count": null, "leetcode_topic": false, "leetcode_topics": null, "applied": true, "company": "Google", "role": "SWE intern", "project_work": false}
"pushed some code today" -> {"leetcode": false, "leetcode_count": null, "leetcode_topic": false, "leetcode_topics": null, "applied": false, "company": null, "role": null, "project_work": true}
"what should i focus on" -> {"leetcode": false, "leetcode_count": null, "leetcode_topic": false, "leetcode_topics": null, "applied": false, "company": null, "role": null, "project_work": false}"""

_INTENT_DEFAULT = {
    "leetcode": False,
    "leetcode_count": None,
    "leetcode_topic": False,
    "leetcode_topics": None,
    "applied": False,
    "company": None,
    "role": None,
    "project_work": False,
}


def get_koda_response(telegram_id: int, user_message: str, user_context: dict) -> str | None:
    user = get_user(telegram_id)
    if user:
        is_premium = user.get("is_premium", False)
        total_message_count = user.get("total_message_count", 0) or 0
        if not is_premium and total_message_count >= 80:
            return None

    system_prompt = build_system_prompt(user_context)
    history = get_recent_messages(telegram_id, limit=20)
    messages = history + [{"role": "user", "content": user_message}]

    try:
        message = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        response_text = message.content[0].text
        save_message(telegram_id, "user", user_message)
        save_message(telegram_id, "assistant", response_text)
        if user:
            update_user(telegram_id, total_message_count=(user.get("total_message_count") or 0) + 1)
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


def classify_intent(user_message: str) -> dict:
    """Run a lightweight classifier to extract activity intent from a message."""
    raw = ""
    try:
        message = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=_INTENT_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = message.content[0].text.strip()
        logger.info(f"classify_intent raw response for {user_message!r}: {raw}")
        clean = clean_json(raw)
        result = json.loads(clean)
        # Ensure all expected keys exist
        final = {**_INTENT_DEFAULT, **result}
        logger.info(f"classify_intent parsed intent: {final}")
        return final
    except json.JSONDecodeError:
        logger.warning(f"classify_intent returned non-JSON for message: {user_message!r} — raw was: {raw!r}")
        return dict(_INTENT_DEFAULT)
    except Exception as e:
        logger.error(f"classify_intent failed for message {user_message!r}: {e}")
        return dict(_INTENT_DEFAULT)


def generate_nudge(user_context: dict) -> str:
    """Generate a personalised evening nudge for a user who hasn't checked in."""
    system = build_system_prompt(user_context)
    name = get_display_name(user_context)
    goals = user_context.get("goals") or "landing a SWE internship"

    prompt = (
        f"Send {name} a short evening nudge — 2-3 lines max. "
        f"They haven't checked in today. Their goal is: {goals}. "
        f"Make it feel personal and specific to them. No generic motivational stuff."
    )

    try:
        message = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=120,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"generate_nudge failed for user {user_context.get('telegram_id')}: {e}")
        return f"hey {name}, you haven't checked in yet today. don't let the streak die."
