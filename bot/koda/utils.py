def clean_json(raw: str) -> str:
    return raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def get_display_name(user: dict) -> str:
    return user.get("name") or user.get("full_name") or user.get("username") or "mate"
