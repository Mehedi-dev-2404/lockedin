import logging
from datetime import date
from db.queries import supabase

logger = logging.getLogger(__name__)


def create_application(telegram_id: int, company: str, role: str) -> dict | None:
    logger.info(f"create_application: {telegram_id} company={company!r} role={role!r}")
    try:
        response = (
            supabase.table("applications")
            .insert({
                "telegram_id": telegram_id,
                "company": company,
                "role": role,
                "status": "applied",
                "applied_at": date.today().isoformat(),
            })
            .execute()
        )
        result = response.data[0] if response.data else None
        if result:
            logger.info(f"create_application succeeded: {telegram_id} id={result.get('id')}")
        else:
            logger.warning(f"create_application returned no data for {telegram_id}")
        return result
    except Exception as e:
        logger.error(f"create_application failed for {telegram_id}: {e}")
        return None


def get_application_count(telegram_id: int) -> int:
    try:
        response = (
            supabase.table("applications")
            .select("id", count="exact")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.count or 0
    except Exception as e:
        logger.error(f"get_application_count failed for {telegram_id}: {e}")
        return 0


def get_applications(telegram_id: int) -> list[dict]:
    try:
        response = (
            supabase.table("applications")
            .select("*")
            .eq("telegram_id", telegram_id)
            .order("applied_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"get_applications failed for {telegram_id}: {e}")
        return []
