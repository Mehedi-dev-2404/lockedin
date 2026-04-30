def clean_json(raw: str) -> str:
    return raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def get_display_name(user: dict) -> str:
    return user.get("name") or user.get("full_name") or user.get("username") or "mate"


def build_user_context(user: dict, streak: dict) -> dict:
    return {
        "telegram_id": user.get("telegram_id"),
        "name": user.get("name"),
        "full_name": user.get("full_name"),
        "username": user.get("username"),
        "year_of_study": user.get("year_of_study"),
        "university": user.get("university"),
        "target_companies": user.get("target_companies"),
        "weak_areas": user.get("weak_areas"),
        "target_type": user.get("target_type"),
        "target_industry": user.get("target_industry"),
        "experience_level": user.get("experience_level"),
        "leetcode_status": user.get("leetcode_status"),
        "accountability_style": user.get("accountability_style"),
        "is_international": user.get("is_international"),
        "github_url": user.get("github_url"),
        "leetcode_progress": user.get("leetcode_progress") or [],
        "leetcode_streak": streak.get("leetcode_streak", 0),
        "applications_streak": streak.get("applications_streak", 0),
        "project_streak": streak.get("project_streak", 0),
        "longest_leetcode": streak.get("longest_leetcode", 0),
        "mode": user.get("mode", "FOCUS"),
    }


def is_vague_input(message: str) -> bool:
    msg = message.lower()
    vague_phrases = [
        "did some", "a bit of", "some leetcode",
        "some coding", "a little"
    ]
    has_vague = any(p in msg for p in vague_phrases)
    has_number = any(char.isdigit() for char in msg)
    has_specific = any(term in msg for term in [
        "two sum", "binary search", "dynamic programming",
        "graph", "tree", "array", "string", "dp", "bfs",
        "dfs", "linked list", "stack", "queue", "heap",
        "python", "java", "javascript", "react", "sql",
        "applied", "interviewed", "oa", "leetcode"
    ])
    return has_vague and not has_number and not has_specific
