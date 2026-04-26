import json
import logging
from config.settings import CLAUDE_MODEL
from bot.koda.anthropic_client import anthropic_client
from bot.koda.utils import clean_json

logger = logging.getLogger(__name__)

_KODA_SYSTEM = (
    "You are Koda — a direct, dry AI accountability agent for CS students grinding for SWE internships. "
    "Lowercase always. No markdown, no asterisks, no bold, no bullet points. "
    "Texting style. Each thought is its own short line. Never corporate."
)

# ---------------------------------------------------------------------------
# Step knowledge — used for clarification, confused handling, and parsing.
# ---------------------------------------------------------------------------

STEP_KNOWLEDGE = {
    0: {
        "capture": "what name the user wants Koda to call them",
        "why": "personalises every message from here on",
        "skippable": False,
        "vocab": {},
        "examples": ["Mehedi", "i'm Alex", "call me J"],
        "ambiguous": {
            "full name given": "use first name only",
            "emoji as name": "ask for something you can actually type",
            "call me anything": "Koda picks something and confirms",
        },
        "options": None,
    },
    1: {
        "capture": "which university they attend and what year of their degree they're in",
        "why": "calibrates advice to where they are — a first year has different priorities than a final year",
        "skippable": False,
        "vocab": {
            "year of study": "which year of their degree they're in — first year, second year, final year, etc.",
            "foundation year / year 0": "a preparatory year before the degree starts — valid, save as 'foundation year'",
        },
        "examples": ["UCL, second year", "Manchester, final year", "Warwick 1st year"],
        "ambiguous": {
            "I'm at a uni in London": "ask which specific one",
            "year 2 vs second year": "same thing",
            "foundation year": "valid — save as foundation year",
        },
        "options": None,
    },
    2: {
        "capture": "whether they're going for a placement year, summer internship, or grad job — and when applications typically open",
        "why": "sets the urgency and timeline for all advice Koda gives",
        "skippable": False,
        "vocab": {
            "placement year": "a full year working at a company as part of your degree, usually between second and third year. also called 'year in industry' or 'sandwich year'.",
            "summer internship": "a shorter role, usually 8-12 weeks over summer between uni years",
            "grad job": "a full-time role you start after finishing your degree",
        },
        "examples": ["placement year, apps open in September", "summer internship", "grad job at a bank"],
        "ambiguous": {
            "year in industry": "placement",
            "sandwich year": "placement",
            "industrial placement": "placement",
            "summer role": "internship",
            "10 week program": "internship",
            "I apply in autumn": "October/November",
            "apps open in the fall": "September/October",
            "not sure yet": "save target_type as 'unknown'",
            "all of them": "save ['placement', 'internship', 'grad']",
        },
        "options": ["placement", "internship", "grad"],
    },
    3: {
        "capture": "whether they are an international student who needs visa sponsorship to work in the UK",
        "why": "many companies don't offer sponsorship — this filters which employers are realistic targets",
        "skippable": False,
        "vocab": {
            "international student": "someone from outside the UK who would need visa sponsorship to work in the UK after graduating",
            "right to work": "legal right to work in the UK without needing employer sponsorship — UK citizens and those with settled/pre-settled status have this",
            "settled status": "EU citizens with settled or pre-settled status generally have the right to work without sponsorship",
        },
        "examples": ["yes I'm from India on a student visa", "no I'm British", "EU student with settled status", "yes", "no", "yeah", "nah"],
        "ambiguous": {
            "I'm from the UK": "false",
            "I'm on a student visa": "true",
            "EU student": "ask if they have settled or pre-settled status",
            "I have the right to work": "false",
            "yes / yeah / yep": "true — they are confirming they are an international student",
            "no / nah / nope": "false — they are confirming they are not an international student",
        },
        "options": None,
    },
    4: {
        "capture": "which specific companies or types of companies they're trying to get into",
        "why": "shapes what Koda prioritises in project and application advice",
        "skippable": False,
        "vocab": {
            "FAANG": "Facebook (Meta), Amazon, Apple, Netflix, Google — shorthand for the top US tech giants",
            "bulge bracket": "Goldman Sachs, JPMorgan, Morgan Stanley — top investment banks",
            "MBB": "McKinsey, Bain, BCG — the top three strategy consultancies",
        },
        "examples": ["Google, Meta, Stripe", "Goldman and Jane Street", "any fintech startup", "not sure yet"],
        "ambiguous": {
            "big companies": "ask to be more specific",
            "idk": "save as ['unknown'] and move on",
        },
        "options": None,
    },
    5: {
        "capture": "which industry they want their technical projects to reflect — finance, bigtech, startup, consultancy, or unknown",
        "why": "determines the anchor project recommendation and how Koda frames all portfolio advice",
        "skippable": False,
        "vocab": {
            "anchor project": "the one main project that speaks directly to your target industry — the centrepiece of your portfolio",
        },
        "examples": ["finance", "big tech", "startups", "not sure"],
        "ambiguous": {
            "banking": "finance",
            "investment banking": "finance",
            "FAANG": "bigtech",
            "my own thing / indie": "startup",
            "not sure / keeping options open": "unknown",
            "both finance and tech": "ask which one they want the anchor project to reflect — they can do both but need a primary focus",
        },
        "options": ["finance", "bigtech", "startup", "consultancy", "unknown"],
    },
    6: {
        "capture": "their current technical experience level — beginner, basics, shipped_locally, or live_in_prod",
        "why": "sets the baseline for how Koda calibrates the difficulty and type of advice it gives",
        "skippable": False,
        "vocab": {
            "shipped locally": "built something that runs on your own machine but never put it online for anyone else to use",
            "live in prod": "something deployed and accessible to real users on the internet",
            "DSA": "data structures and algorithms — the coding problems companies test in interviews",
        },
        "examples": ["just started learning Python", "know the basics but haven't shipped anything", "got a project on Railway with 20 users"],
        "ambiguous": {
            "only done tutorials": "beginner",
            "I know Python": "basics",
            "my projects only run on my laptop": "shipped_locally",
            "I have a website": "ask if it's live or just local",
            "Discord bot with 200 users": "live_in_prod",
        },
        "options": ["beginner", "basics", "shipped_locally", "live_in_prod"],
    },
    7: {
        "capture": "whether they have a GitHub account and the URL if they want to share it",
        "why": "GitHub is how most companies look at technical ability before interviews — not having one is a red flag",
        "skippable": True,
        "vocab": {
            "GitHub": "a website where developers store and share code publicly. Think of it as a portfolio for developers. github.com",
        },
        "examples": ["yes github.com/mehedi123", "no I don't have one yet", "yeah but it's empty honestly"],
        "ambiguous": {
            "I have one but it's empty": "save has_github=true, note it's empty — fine, we'll fix it",
            "what's GitHub": "explain it simply, tell them we'll help set one up, save has_github=false and move on",
            "non-GitHub URL": "ask if they mean their GitHub specifically",
        },
        "options": None,
    },
    8: {
        "capture": "where they're at with LeetCode — grinding, just started, or haven't touched it",
        "why": "most technical interviews at top companies use LeetCode-style problems — Koda needs to know the gap",
        "skippable": False,
        "vocab": {
            "LeetCode": "a website with coding interview practice problems. Companies like Google, Amazon, and Goldman use similar questions in technical interviews. Problems are rated easy, medium, or hard.",
            "grinding": "doing LeetCode problems regularly — daily or near-daily",
        },
        "examples": ["grinding every day", "just started, done about 10", "haven't opened it"],
        "ambiguous": {
            "I do a few a week": "grinding",
            "I've done 3": "started",
            "I've done 47 problems": "grinding (>20 = grinding, >0 = started, 0 = not_started)",
            "I hate leetcode": "acknowledge it, still need a status",
            "I'm not doing it": "not_started",
        },
        "options": ["grinding", "started", "not_started"],
    },
    9: {
        "capture": "which areas of their preparation they know are currently weak",
        "why": "determines what Koda focuses on and what it pushes hardest",
        "skippable": False,
        "vocab": {
            "DSA": "data structures and algorithms — arrays, trees, graphs, sorting. The stuff companies test in coding interviews.",
            "system design": "designing large-scale systems. 'How would you build Twitter?' type questions. More common for experienced roles.",
            "behavioural": "'Tell me about a time when...' interview questions. Soft skills, teamwork stories, conflict examples.",
            "networking": "not computer networking. Meeting people in the industry — LinkedIn, events, referrals.",
        },
        "examples": ["DSA and system design", "behavioural interviews", "literally everything", "building and shipping projects"],
        "ambiguous": {
            "everything / idk": "save all standard weak areas",
            "nothing / I'm good at everything": "push back once lightly — if they insist, save empty array",
        },
        "options": ["DSA", "system_design", "behavioural", "building_projects", "networking", "frontend", "backend", "databases", "other"],
    },
    10: {
        "capture": "how hard they want Koda to be on them — default, no_mercy, or light_touch",
        "why": "sets Koda's tone for the entire engagement",
        "skippable": False,
        "vocab": {
            "default": "Koda checks in daily, calls you out on missed streaks, pushes you but isn't brutal about it",
            "no_mercy": "Koda will call you out every single time, no softening, no excuses accepted — escalates the longer you've been quiet",
            "light_touch": "gentle daily nudges, more encouraging tone, less confrontational",
        },
        "examples": ["default", "no mercy, be brutal", "light touch please", "somewhere in the middle"],
        "ambiguous": {
            "be brutal": "no_mercy",
            "be nice": "light_touch",
            "surprise me": "default",
            "the normal one": "default",
        },
        "options": ["default", "no_mercy", "light_touch"],
    },
    11: {
        "capture": "what time each day to send the check-in nudge",
        "why": "ensures Koda messages at a time the user will actually see it",
        "skippable": False,
        "vocab": {},
        "examples": ["8pm", "20:00", "9am", "half 7 in the evening"],
        "ambiguous": {
            "evening": "19:00",
            "morning": "08:00",
            "night": "21:00",
            "late": "22:00",
            "anytime / don't care": "default to 20:00",
        },
        "options": None,
    },
}

# Required fields that must be non-null for a step to count as answered.
STEP_REQUIRED_FIELDS = {
    0: ["name"],
    1: ["university", "year_of_study"],
    2: ["target_type"],
    3: ["is_international"],
    4: ["target_companies"],
    5: ["target_industry"],
    6: ["experience_level"],
    7: ["has_github"],
    8: ["leetcode_status"],
    9: ["weak_areas"],
    10: ["accountability_style"],
    11: ["nudge_time"],
}

SKIPPABLE_STEPS = {7}  # github step — URL skippable, but has_github still required


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call(system: str, user_message: str, max_tokens: int = 300) -> dict | None:
    try:
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        clean = clean_json(raw)
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning(f"onboarding_parser non-JSON response for: {user_message[:80]!r}")
        return None
    except Exception as e:
        logger.error(f"onboarding_parser._call failed: {e}")
        return None


def _call_text(system: str, user_message: str, max_tokens: int = 250) -> str:
    try:
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"onboarding_parser._call_text failed: {e}")
        return ""


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    lines = []
    for msg in history[-10:]:  # last 10 for context without bloat
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_knowledge(step: int) -> str:
    k = STEP_KNOWLEDGE.get(step, {})
    parts = [f"Trying to capture: {k.get('capture', '?')}"]
    parts.append(f"Why it matters: {k.get('why', '?')}")
    if k.get("vocab"):
        vocab_lines = "\n".join(f"  - {t}: {d}" for t, d in k["vocab"].items())
        parts.append(f"Terms to know:\n{vocab_lines}")
    if k.get("examples"):
        parts.append(f"Valid answer examples: {', '.join(k['examples'])}")
    if k.get("ambiguous"):
        amb_lines = "\n".join(f"  - '{k}' → {v}" for k, v in k["ambiguous"].items())
        parts.append(f"Ambiguous input mappings:\n{amb_lines}")
    if k.get("options"):
        parts.append(f"Valid options: {', '.join(k['options'])}")
    return "\n".join(parts)


def _summarise_user_data(user: dict) -> str:
    fields = {
        "name": user.get("name"),
        "university": user.get("university"),
        "year": user.get("year_of_study"),
        "target type": user.get("target_type"),
        "international": user.get("is_international"),
        "target companies": user.get("target_companies"),
        "industry": user.get("target_industry"),
        "experience": user.get("experience_level"),
        "github": user.get("github_url") or ("yes" if user.get("has_github") else None),
        "leetcode": user.get("leetcode_status"),
        "weak areas": user.get("weak_areas"),
        "accountability": user.get("accountability_style"),
        "nudge time": user.get("nudge_time"),
    }
    lines = [f"{k}: {v}" for k, v in fields.items() if v is not None]
    return "\n".join(lines) if lines else "nothing captured yet"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(message: str, step: int, history: list[dict]) -> str:
    """Classify the user's message into one of 10 intent types. Pure Claude — no keyword matching."""
    step_capture = STEP_KNOWLEDGE.get(step, {}).get("capture", "the current question")
    history_text = _format_history(history)

    system = f"""You are classifying a user's message during a conversational onboarding flow.
Koda just asked the user about: {step_capture}

Recent conversation:
{history_text}

Classify the user's message into exactly one of these categories:
- answer: user is attempting to respond to the question, even if vague, indirect, or using different words
- clarification: user is asking what something means or wants more context before answering
- correction: user is going back to change or correct something they said earlier in the conversation
- skip: user explicitly wants to skip the question or says it doesn't apply to them
- confused: user seems lost, frustrated, overwhelmed, or genuinely unsure what is being asked
- off_topic: user is asking or saying something completely unrelated to the onboarding question
- multi_answer: user has answered this question AND one or more future questions in the same message
- test: user is clearly testing or probing the bot ("what if I say banana", "say something random")
- abuse: user is being hostile, sending repeated nonsense, or trying to break the bot
- non_text: user sent only emoji, a sticker placeholder, or content that cannot be read as text

Respond with ONLY one word from the list above. Nothing else."""

    try:
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=10,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        result = response.content[0].text.strip().lower()
        valid = {"answer", "clarification", "correction", "skip", "confused",
                 "off_topic", "multi_answer", "test", "abuse", "non_text"}
        if result in valid:
            return result
        logger.warning(f"classify_intent unexpected value: {result!r} — defaulting to answer")
        return "answer"
    except Exception as e:
        logger.error(f"classify_intent failed: {e}")
        return "answer"


def parse_step(step: int, message: str, history: list[dict]) -> dict | None:
    """
    Extract structured data from the user's message. Attempts to capture data for the
    current step AND any other steps visible in the same message (multi_answer support).
    Returns a flat dict of non-null field values, or None if nothing useful was extracted.
    """
    history_text = _format_history(history)
    knowledge_text = _format_knowledge(step)

    system = """You are extracting structured profile data from a user's message during onboarding.
Extract ONLY what is clearly stated or strongly implied. Do not guess or hallucinate values.
Return ONLY valid JSON. No explanation, no markdown fences — just the JSON object.
Include only the fields you actually extracted. Omit fields with no data."""

    all_fields_doc = """
Available fields and their types:
- name: string (first name only)
- university: string
- year_of_study: string (e.g. "2nd year", "final year", "foundation year")
- target_type: string, one of: placement, internship, grad, unknown — or array if multiple
- app_deadline: string (free text e.g. "September", "already open", "not sure")
- is_international: boolean
- target_companies: array of strings
- target_industry: string, one of: finance, bigtech, startup, consultancy, unknown
- experience_level: string, one of: beginner, basics, shipped_locally, live_in_prod
- has_github: boolean
- github_url: string or null
- leetcode_status: string, one of: grinding, started, not_started
- weak_areas: array of strings from: DSA, system_design, behavioural, building_projects, networking, frontend, backend, databases, other
- accountability_style: string, one of: default, no_mercy, light_touch
- nudge_time: string in 24hr format HH:MM"""

    prompt = f"""Current onboarding step context:
{knowledge_text}

Conversation history:
{history_text}

User's message: "{message}"

{all_fields_doc}

Extract all data you can find across any fields. Focus on the current step but capture anything else that's clearly stated.
Return a JSON object with only the fields you found. Example: {{"name": "Mehedi", "university": "UCL"}}"""

    result = _call(system, prompt, max_tokens=400)
    if not result:
        return None
    # Filter to only known fields and non-None values
    known_fields = {
        "name", "university", "year_of_study", "target_type", "app_deadline",
        "is_international", "target_companies", "target_industry", "experience_level",
        "has_github", "github_url", "leetcode_status", "weak_areas",
        "accountability_style", "nudge_time",
    }
    cleaned = {k: v for k, v in result.items() if k in known_fields and v is not None}
    return cleaned if cleaned else None


def parse_correction(message: str, history: list[dict], user: dict) -> dict | None:
    """
    Parse a correction message. Returns dict with the corrected field(s) and new value(s),
    or None if no clear correction could be extracted.
    """
    history_text = _format_history(history)
    current_data = _summarise_user_data(user)

    system = """You are detecting a correction to previously given information during onboarding.
Return ONLY valid JSON with the field(s) being corrected and their new values.
Use the same field names as the profile schema. No explanation."""

    prompt = f"""User's current profile data:
{current_data}

Conversation history:
{history_text}

User says: "{message}"

They appear to be correcting something. Extract what field they're changing and what the new value is.
Return JSON with only the corrected field(s). Example: {{"university": "UCL"}} or {{"target_type": "grad"}}
If you can't determine what's being corrected, return {{}}"""

    result = _call(system, prompt, max_tokens=200)
    if not result:
        return None
    known_fields = {
        "name", "university", "year_of_study", "target_type", "app_deadline",
        "is_international", "target_companies", "target_industry", "experience_level",
        "has_github", "github_url", "leetcode_status", "weak_areas",
        "accountability_style", "nudge_time",
    }
    cleaned = {k: v for k, v in result.items() if k in known_fields and v is not None}
    return cleaned if cleaned else None


def generate_response(
    intent: str,
    step: int,
    user_message: str,
    history: list[dict],
    user_data: dict | None = None,
) -> list[str]:
    """
    Generate Koda's response for a given intent. Returns a list of strings where each
    string is one Telegram message. Plain text only — no markdown, no asterisks.
    """
    knowledge = STEP_KNOWLEDGE.get(step, {})
    step_capture = knowledge.get("capture", "the current question")
    history_text = _format_history(history)
    knowledge_text = _format_knowledge(step)

    base_rules = (
        "Plain text only. No asterisks, no markdown, no bold, no bullet points. "
        "Each Telegram message on its own line. Lowercase. "
        "Koda's voice: direct, dry, occasionally sharp. Never corporate."
    )

    if intent == "clarification":
        vocab = knowledge.get("vocab", {})
        vocab_text = "\n".join(f"- {t}: {d}" for t, d in vocab.items()) if vocab else "(no specific vocabulary — use common sense)"
        prompt = f"""User asked for clarification: "{user_message}"
Koda was asking about: {step_capture}

Relevant definitions:
{vocab_text}

Conversation:
{history_text}

Write Koda's response. Rules:
- Explain what you're asking in 1-2 plain sentences. Use the definitions above. Be specific.
- Give one concrete example of a valid answer.
- Re-ask in ONE short casual line at the end. Not the full original question — just a natural short re-ask.
- {base_rules}
- 3-4 lines total maximum."""

    elif intent == "off_topic":
        user_summary = _summarise_user_data(user_data) if user_data else ""
        prompt = f"""User went off topic: "{user_message}"
Koda is trying to find out: {step_capture}

What Koda knows about them so far:
{user_summary if user_summary else "(nothing yet)"}

Conversation:
{history_text}

Write Koda's response. Rules:
- If the user is asking what data Koda has on them, give a brief plain text summary of the fields above that are filled in, then continue.
- Otherwise: acknowledge in one line with light humour if it fits naturally. Tell them we'll get to it after setup. Re-ask the current question in one short casual line.
- {base_rules}
- 2-3 lines max."""

    elif intent == "skip":
        skippable = knowledge.get("skippable", False)
        if skippable:
            return []
        prompt = f"""User wants to skip: "{user_message}"
Koda needs: {step_capture}
This step cannot be skipped.

Write Koda's response. Rules:
- In one line, explain in plain English why this is needed.
- Re-ask simply in one short line.
- {base_rules}
- 2 lines max."""

    elif intent == "test":
        prompt = f"""User is clearly testing the bot: "{user_message}"
Koda is asking about: {step_capture}

Write Koda's response. Rules:
- Play along in character for one line. Dry humour only — don't overdo it.
- Steer back to the question in one short line.
- {base_rules}
- 2 lines max."""

    elif intent == "abuse":
        prompt = f"""User sent something hostile or is being difficult: "{user_message}"
Koda is asking about: {step_capture}

Write Koda's response. Rules:
- Respond once, calmly and firmly. Do not get defensive or apologetic.
- One line only.
- Then re-ask the question simply in one line.
- {base_rules}"""

    elif intent == "confused":
        # Per design: ask what they're confused about rather than re-explaining everything.
        prompt = f"""The user seems confused or lost during onboarding. Koda was asking about: {step_capture}
User said: "{user_message}"

Write ONE short line asking what specifically is confusing them.
Examples: "what part's throwing you off?" / "what are you not getting?" / "where are you stuck?"
- Do not re-explain the question. Do not re-ask it. Just the short probe.
- {base_rules}"""

    elif intent == "non_text":
        return ["can't read that. just type it out."]

    else:
        return []

    response_text = _call_text(_KODA_SYSTEM, prompt, max_tokens=250)
    if not response_text:
        # Fallback if Claude fails — log already done in _call_text
        fallback_map = {
            "clarification": f"it means: {step_capture}. just give me your answer.",
            "off_topic": f"we'll get to that. first — {step_capture}.",
            "skip": f"can't skip this one. {step_capture}.",
            "test": f"noted. now — {step_capture}.",
            "abuse": f"i need an actual answer. {step_capture}.",
            "confused": "what part's throwing you off?",
        }
        return [fallback_map.get(intent, "try again.")]

    return [line.strip() for line in response_text.split("\n") if line.strip()]


def generate_summary(user_data: dict) -> str:
    """Generate a personalised 2-3 line profile summary in Koda's voice for the completion sequence."""
    name = user_data.get("name") or "mate"
    target_type = user_data.get("target_type") or "internship"
    companies = user_data.get("target_companies") or []
    industry = user_data.get("target_industry") or "unknown"
    experience = user_data.get("experience_level") or "basics"
    leetcode = user_data.get("leetcode_status") or "not_started"
    weak_areas = user_data.get("weak_areas") or []
    is_international = user_data.get("is_international")

    companies_str = ", ".join(companies[:3]) if companies else "open"
    weak_str = ", ".join(weak_areas[:3]) if weak_areas else "not specified"
    intl = " (needs sponsorship)" if is_international else ""

    prompt = (
        f"Write a 2-3 line profile summary for {name} in Koda's voice. "
        f"Direct, lowercase, specific to their profile. Each thought on its own line. "
        f"Reference their actual target companies or weak areas — make it feel like you actually know them. "
        f"End with something that naturally opens the conversation about their anchor project.\n\n"
        f"Profile:\n"
        f"- Target: {target_type}{intl}\n"
        f"- Companies: {companies_str}\n"
        f"- Industry: {industry}\n"
        f"- Experience: {experience}\n"
        f"- LeetCode: {leetcode}\n"
        f"- Weak areas: {weak_str}"
    )

    try:
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=_KODA_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"generate_summary failed: {e}")
        return (
            f"aight {name}, i've got your full profile.\n"
            f"now let's talk about the thing that'll actually move the needle — your anchor project."
        )
