import logging
from datetime import date, timedelta
from db.queries import supabase

logger = logging.getLogger(__name__)


def get_streak(telegram_id: int) -> dict | None:
    try:
        response = (
            supabase.table("streaks")
            .select("*")
            .eq("telegram_id", telegram_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"get_streak failed for {telegram_id}: {e}")
        return None


def create_streak(telegram_id: int) -> dict | None:
    try:
        response = (
            supabase.table("streaks")
            .insert({
                "telegram_id": telegram_id,
                "leetcode_streak": 0,
                "applications_streak": 0,
                "project_streak": 0,
            })
            .execute()
        )
        result = response.data[0] if response.data else None
        if result:
            logger.info(f"create_streak succeeded for {telegram_id}")
        else:
            logger.warning(f"create_streak returned no data for {telegram_id}")
        return result
    except Exception as e:
        logger.error(f"create_streak failed for {telegram_id}: {e}")
        return None


def update_streak(telegram_id: int, **kwargs) -> dict | None:
    try:
        response = (
            supabase.table("streaks")
            .update(kwargs)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"update_streak failed for {telegram_id}: {e}")
        return None


def _compute_new_streak(current: int, last_date_str: str | None) -> int:
    """Returns the new streak value based on last activity date."""
    today = date.today()
    if not last_date_str:
        return 1
    last = date.fromisoformat(last_date_str) if isinstance(last_date_str, str) else last_date_str
    if last == today:
        return current  # already counted today
    if last == today - timedelta(days=1):
        return current + 1  # continuing
    return 1  # broken


def update_leetcode_streak(telegram_id: int) -> tuple[int, bool]:
    """
    Increments the leetcode streak if not already counted today.
    Returns (new_streak, is_milestone) where is_milestone is True at multiples of 7.
    """
    streak = get_streak(telegram_id)
    if not streak:
        logger.error(f"update_leetcode_streak: no streak row found for {telegram_id} — was create_streak called during onboarding?")
        return 0, False

    current = streak.get("leetcode_streak", 0)
    last_date_str = streak.get("last_leetcode_date")
    today = date.today()

    # Already logged today — no-op
    if last_date_str:
        last = date.fromisoformat(last_date_str) if isinstance(last_date_str, str) else last_date_str
        if last == today:
            logger.debug(f"update_leetcode_streak: already counted today for {telegram_id}, streak={current}")
            return current, False

    new_streak = _compute_new_streak(current, last_date_str)
    longest = max(streak.get("longest_leetcode", 0), new_streak)

    logger.info(f"update_leetcode_streak: {telegram_id} streak {current} -> {new_streak} (last={last_date_str})")
    update_streak(
        telegram_id,
        leetcode_streak=new_streak,
        last_leetcode_date=today.isoformat(),
        longest_leetcode=longest,
    )

    is_milestone = new_streak > 0 and new_streak % 7 == 0
    return new_streak, is_milestone


def update_applications_streak(telegram_id: int) -> tuple[int, bool]:
    """
    Increments the applications streak if not already counted today.
    Returns (new_streak, is_milestone).
    """
    streak = get_streak(telegram_id)
    if not streak:
        logger.error(f"update_applications_streak: no streak row found for {telegram_id}")
        return 0, False

    current = streak.get("applications_streak", 0)
    last_date_str = streak.get("last_application_date")
    today = date.today()

    if last_date_str:
        last = date.fromisoformat(last_date_str) if isinstance(last_date_str, str) else last_date_str
        if last == today:
            logger.debug(f"update_applications_streak: already counted today for {telegram_id}, streak={current}")
            return current, False

    new_streak = _compute_new_streak(current, last_date_str)
    longest = max(streak.get("longest_applications", 0), new_streak)

    logger.info(f"update_applications_streak: {telegram_id} streak {current} -> {new_streak} (last={last_date_str})")
    update_streak(
        telegram_id,
        applications_streak=new_streak,
        last_application_date=today.isoformat(),
        longest_applications=longest,
    )

    is_milestone = new_streak > 0 and new_streak % 7 == 0
    return new_streak, is_milestone


def update_project_streak(telegram_id: int) -> tuple[int, bool]:
    """
    Increments the project streak if not already counted today.
    Returns (new_streak, is_milestone).
    """
    streak = get_streak(telegram_id)
    if not streak:
        logger.error(f"update_project_streak: no streak row found for {telegram_id}")
        return 0, False

    current = streak.get("project_streak", 0)
    last_date_str = streak.get("last_project_date")
    today = date.today()

    if last_date_str:
        last = date.fromisoformat(last_date_str) if isinstance(last_date_str, str) else last_date_str
        if last == today:
            logger.debug(f"update_project_streak: already counted today for {telegram_id}, streak={current}")
            return current, False

    new_streak = _compute_new_streak(current, last_date_str)
    longest = max(streak.get("longest_project", 0), new_streak)

    logger.info(f"update_project_streak: {telegram_id} streak {current} -> {new_streak} (last={last_date_str})")
    update_streak(
        telegram_id,
        project_streak=new_streak,
        last_project_date=today.isoformat(),
        longest_project=longest,
    )

    is_milestone = new_streak > 0 and new_streak % 7 == 0
    return new_streak, is_milestone
