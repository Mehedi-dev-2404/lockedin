import logging
from db.queries import supabase

logger = logging.getLogger(__name__)


def save_message(telegram_id: int, role: str, content: str, message_type: str = "conversation") -> None:
    try:
        supabase.table("messages").insert({
            "user_id": telegram_id,
            "role": role,
            "content": content,
            "message_type": message_type,
        }).execute()
    except Exception as e:
        logger.error(f"save_message failed for {telegram_id}: {e}")


def delete_onboarding_messages(telegram_id: int) -> None:
    try:
        supabase.table("messages").delete().eq("user_id", telegram_id).eq("message_type", "onboarding").execute()
    except Exception as e:
        logger.error(f"delete_onboarding_messages failed for {telegram_id}: {e}")


def get_recent_messages(telegram_id: int, limit: int = 20) -> list[dict]:
    try:
        response = (
            supabase.table("messages")
            .select("role, content")
            .eq("user_id", telegram_id)
            .eq("message_type", "conversation")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed(response.data or []))
    except Exception as e:
        logger.error(f"get_recent_messages failed for {telegram_id}: {e}")
        return []
