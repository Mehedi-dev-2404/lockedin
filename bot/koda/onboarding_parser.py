import json
import logging
import anthropic
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_KODA_SYSTEM = (
    "You are Koda — a direct, dry AI accountability agent for CS students. "
    "Lowercase. No fluff. Texting style."
)


def _call(system: str, user_message: str, max_tokens: int = 200) -> dict | None:
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        clean = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning(f"onboarding_parser non-JSON for: {user_message!r}")
        return None
    except Exception as e:
        logger.error(f"onboarding_parser._call failed: {e}")
        return None


def _call_text(system: str, user_message: str, max_tokens: int = 200) -> str:
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"onboarding_parser._call_text failed: {e}")
        return ""


def classify_intent(user_message: str, step_context: str) -> str:
    """Classify user message as: answer | clarification_request | out_of_scope | confused."""
    system = f"""You are classifying a user's message during a bot setup conversation.
Koda just asked the user about: {step_context}

Classify their reply into exactly one category:
- answer: they are attempting to answer the question, even if vague, indirect, or using different words
- clarification_request: they are asking what something means, or asking for more info before answering
- out_of_scope: they are saying or asking something completely unrelated to the question
- confused: they seem lost, frustrated, unsure what's being asked, or expressing that they don't know what to say

Respond with ONLY one of those four words. Nothing else.

Examples (for "which university and year are you in"):
"second year UCL" -> answer
"UCL" -> answer
"I'm at Manchester in my third year" -> answer
"what do you mean by year?" -> clarification_request
"does it matter which course I'm doing?" -> clarification_request
"what's the best programming language?" -> out_of_scope
"I don't know what to put here" -> confused
"idk" -> confused
"lol no idea" -> confused"""

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=10,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        result = response.content[0].text.strip().lower()
        if result in ("answer", "clarification_request", "out_of_scope", "confused"):
            return result
        logger.warning(f"classify_intent got unexpected value: {result!r}")
        return "answer"
    except Exception as e:
        logger.error(f"classify_intent failed: {e}")
        return "answer"


def generate_clarification_response(user_message: str, step_context: str) -> str:
    """Generate a Koda response to a clarification request — explains the question then re-asks with fresh phrasing."""
    prompt = (
        f'The user asked: "{user_message}"\n\n'
        f"Koda was trying to find out: {step_context}\n\n"
        f"Write Koda's response. It should: explain what you're asking in plain English "
        f"with one concrete example, then re-ask the question naturally using different phrasing from before. "
        f"2-3 short messages separated by newlines. Lowercase. Dry, direct tone. No fluff. "
        f"Don't start with 'so' or 'basically'."
    )
    return _call_text(_KODA_SYSTEM, prompt, max_tokens=220)


def generate_out_of_scope_response(user_message: str, step_context: str) -> str:
    """Generate a Koda response when the user goes off-topic — brief acknowledgement, redirect, re-ask."""
    prompt = (
        f'The user said: "{user_message}"\n\n'
        f"This is unrelated to what Koda just asked. Koda is trying to find out: {step_context}\n\n"
        f"Write Koda's response. Acknowledge their message in one short line (don't dismiss it), "
        f"say you'll get to it once setup is done, then re-ask the question with slightly different phrasing. "
        f"2-3 lines max. Lowercase. Keep the redirect light — not dismissive."
    )
    return _call_text(_KODA_SYSTEM, prompt, max_tokens=180)


def generate_confused_response(user_message: str, step_context: str) -> str:
    """Generate a Koda response when the user seems confused or lost — reset, explain, re-ask simply."""
    prompt = (
        f'The user said: "{user_message}" — they seem confused or unsure.\n\n'
        f"Koda was trying to find out: {step_context}\n\n"
        f"Write Koda's response. Acknowledge that it's a fair question to be unsure about (1 line), "
        f"explain simply what Koda is trying to understand and why it matters for their internship prep (1-2 lines), "
        f"then re-ask more simply with a concrete example. "
        f"Lowercase. Direct but warm. Not condescending."
    )
    return _call_text(_KODA_SYSTEM, prompt, max_tokens=220)


def parse_name(raw: str) -> dict | None:
    system = """Extract the person's name from their message. Respond ONLY with valid JSON, nothing else.
{"name": "string or null"}
Examples:
"i'm mehedi" -> {"name": "Mehedi"}
"call me alex" -> {"name": "Alex"}
"john smith" -> {"name": "John"}
"mehedi" -> {"name": "Mehedi"}
If you cannot extract a clear name, return {"name": null}."""
    result = _call(system, raw)
    if result and result.get("name"):
        return result
    return None


def parse_university_year(raw: str) -> dict | None:
    system = """Extract university name and year of study from the message. Respond ONLY with valid JSON, nothing else.
{"university": "string or null", "year_of_study": "string or null"}
Examples:
"UCL, second year" -> {"university": "UCL", "year_of_study": "2nd year"}
"I'm at Manchester doing my third year" -> {"university": "University of Manchester", "year_of_study": "3rd year"}
"King's College London, final year" -> {"university": "King's College London", "year_of_study": "final year"}
"Warwick, 1st year" -> {"university": "University of Warwick", "year_of_study": "1st year"}
If you cannot extract either field, return null for that field."""
    result = _call(system, raw)
    if result and (result.get("university") or result.get("year_of_study")):
        return result
    return None


def parse_target_type_deadline(raw: str) -> dict | None:
    system = """Extract target_type and app_deadline from the message. Interpret intent flexibly — don't require exact keywords.
Respond ONLY with valid JSON, nothing else.
target_type must be one of: placement, internship, grad
app_deadline is a free-text string for when applications open (e.g. "September 2025", "already open", "not sure").
{"target_type": "placement|internship|grad|null", "app_deadline": "string or null"}
Examples:
"placement year, apps open in September" -> {"target_type": "placement", "app_deadline": "September"}
"I want to do a year in industry" -> {"target_type": "placement", "app_deadline": "not sure"}
"sandwich year" -> {"target_type": "placement", "app_deadline": "not sure"}
"industrial placement" -> {"target_type": "placement", "app_deadline": "not sure"}
"summer internship, they open around Jan" -> {"target_type": "internship", "app_deadline": "January"}
"10 week summer program" -> {"target_type": "internship", "app_deadline": "not sure"}
"grad job, already applying" -> {"target_type": "grad", "app_deadline": "already open"}
"full time after graduation" -> {"target_type": "grad", "app_deadline": "not sure"}
"internship, I apply in autumn" -> {"target_type": "internship", "app_deadline": "October/November"}
"apps open in the fall" -> {"target_type": null, "app_deadline": "September/October"}
"not sure when, probably next year" -> {"target_type": null, "app_deadline": "next year"}
If you cannot determine target_type, return {"target_type": null, "app_deadline": null}."""
    result = _call(system, raw)
    if result and result.get("target_type"):
        return result
    return None


def parse_international(raw: str) -> dict | None:
    system = """Determine if the person is an international student. Respond ONLY with valid JSON, nothing else.
{"is_international": true or false or null}
Examples:
"yes I'm international, from India" -> {"is_international": true}
"nah I'm from the UK" -> {"is_international": false}
"no" -> {"is_international": false}
"yeah international student" -> {"is_international": true}
"domestic" -> {"is_international": false}
If genuinely cannot tell, return {"is_international": null}."""
    result = _call(system, raw)
    if result and result.get("is_international") is not None:
        return result
    return None


def parse_target_companies(raw: str) -> dict | None:
    system = """Extract a list of target companies or company types. Respond ONLY with valid JSON, nothing else.
{"target_companies": ["string", ...]}
Be specific — use actual company names where given. Accept vague categories too.
Examples:
"Google, Meta, Stripe" -> {"target_companies": ["Google", "Meta", "Stripe"]}
"FAANG and some fintech" -> {"target_companies": ["FAANG", "fintech"]}
"Goldman, Jane Street, Citadel" -> {"target_companies": ["Goldman Sachs", "Jane Street", "Citadel"]}
"honestly don't know yet, any big tech" -> {"target_companies": ["big tech"]}
"JP Morgan, Barclays, any bank tbh" -> {"target_companies": ["JP Morgan", "Barclays", "banking"]}
Always return at least one entry."""
    result = _call(system, raw)
    if result and result.get("target_companies"):
        return result
    return None


def parse_target_industry(raw: str) -> dict | None:
    system = """Map the person's target industry to exactly one of: finance, bigtech, startup, consultancy, unknown.
Respond ONLY with valid JSON, nothing else.
{"target_industry": "finance|bigtech|startup|consultancy|unknown"}
Examples:
"finance, Goldman and Jane Street type roles" -> {"target_industry": "finance"}
"big tech, Google Facebook etc" -> {"target_industry": "bigtech"}
"startups, I want to move fast and ship" -> {"target_industry": "startup"}
"consultancy like Accenture or Deloitte" -> {"target_industry": "consultancy"}
"not sure yet, keeping doors open" -> {"target_industry": "unknown"}
"FAANG" -> {"target_industry": "bigtech"}
"hedge funds, prop trading" -> {"target_industry": "finance"}"""
    result = _call(system, raw)
    if result and result.get("target_industry"):
        return result
    return None


def parse_experience_level(raw: str) -> dict | None:
    system = """Map the person's technical experience to exactly one of: beginner, basics, shipped_locally, live_in_prod.
Interpret intent flexibly — infer from what they describe, don't require exact phrases.
Respond ONLY with valid JSON, nothing else.
{"experience_level": "beginner|basics|shipped_locally|live_in_prod"}
Definitions:
- beginner: complete beginner, just started or never coded seriously
- basics: knows fundamentals but hasn't built or shipped anything real yet
- shipped_locally: built projects that run locally on their machine, nothing deployed publicly
- live_in_prod: has something live on the internet with real users
Examples:
"complete beginner, just started learning Python" -> {"experience_level": "beginner"}
"only done tutorials, no real projects" -> {"experience_level": "beginner"}
"know Python and some web stuff but never really built anything" -> {"experience_level": "basics"}
"I can code but haven't made anything real" -> {"experience_level": "basics"}
"done the fundamentals, working on my first project" -> {"experience_level": "basics"}
"built a few projects locally, none deployed" -> {"experience_level": "shipped_locally"}
"got some stuff on my machine but never put anything online" -> {"experience_level": "shipped_locally"}
"my projects only run on my laptop" -> {"experience_level": "shipped_locally"}
"I have a SaaS with 50 users" -> {"experience_level": "live_in_prod"}
"got a portfolio site live and a small app deployed" -> {"experience_level": "live_in_prod"}
"I shipped a Discord bot that 200 people use" -> {"experience_level": "live_in_prod"}
"something on Vercel/Heroku/Railway with real users" -> {"experience_level": "live_in_prod"}"""
    result = _call(system, raw)
    if result and result.get("experience_level"):
        return result
    return None


def parse_github(raw: str) -> dict | None:
    system = """Determine if the person has a GitHub and extract the URL if provided.
Respond ONLY with valid JSON, nothing else.
{"has_github": true or false, "github_url": "string or null"}
Examples:
"yes github.com/mehedi" -> {"has_github": true, "github_url": "github.com/mehedi"}
"yeah it's github.com/alex123" -> {"has_github": true, "github_url": "github.com/alex123"}
"no I don't have one" -> {"has_github": false, "github_url": null}
"nah" -> {"has_github": false, "github_url": null}
"yes but I don't want to share it" -> {"has_github": true, "github_url": null}
"https://github.com/jsmith" -> {"has_github": true, "github_url": "github.com/jsmith"}"""
    result = _call(system, raw)
    if result and result.get("has_github") is not None:
        return result
    return None


def parse_leetcode_status(raw: str) -> dict | None:
    system = """Map the person's LeetCode status to exactly one of: grinding, started, not_started.
Respond ONLY with valid JSON, nothing else.
{"leetcode_status": "grinding|started|not_started"}
Examples:
"I grind it every day, done 200 problems" -> {"leetcode_status": "grinding"}
"yeah been grinding neetcode" -> {"leetcode_status": "grinding"}
"just started, done like 10 problems" -> {"leetcode_status": "started"}
"haven't touched it" -> {"leetcode_status": "not_started"}
"nah not really started yet" -> {"leetcode_status": "not_started"}
"done a few easy ones" -> {"leetcode_status": "started"}"""
    result = _call(system, raw)
    if result and result.get("leetcode_status"):
        return result
    return None


def parse_weak_areas(raw: str) -> dict | None:
    system = """Extract a list of weak areas the person wants to improve. Respond ONLY with valid JSON, nothing else.
{"weak_areas": ["string", ...]}
Common weak areas: DSA, system design, behavioural interviews, building projects, networking, CV writing, frontend, backend, databases, algorithms, time management, communication.
Examples:
"DSA and system design for sure" -> {"weak_areas": ["DSA", "system design"]}
"behavioural interviews and I can't build projects fast enough" -> {"weak_areas": ["behavioural interviews", "building projects"]}
"honestly everything lol" -> {"weak_areas": ["DSA", "system design", "behavioural interviews", "building projects"]}
"mostly DSA, never touched system design" -> {"weak_areas": ["DSA", "system design"]}
Always return at least one entry."""
    result = _call(system, raw)
    if result and result.get("weak_areas"):
        return result
    return None


def parse_accountability_style(raw: str) -> dict | None:
    system = """Map the person's preferred accountability style to exactly one of: default, no_mercy, light_touch.
Respond ONLY with valid JSON, nothing else.
{"accountability_style": "default|no_mercy|light_touch"}
Examples:
"default is fine" -> {"accountability_style": "default"}
"no mercy, be brutal with me" -> {"accountability_style": "no_mercy"}
"light touch please, I'm sensitive lol" -> {"accountability_style": "light_touch"}
"push me hard, don't go easy" -> {"accountability_style": "no_mercy"}
"gentle nudges" -> {"accountability_style": "light_touch"}
"somewhere in the middle" -> {"accountability_style": "default"}
"just the normal one" -> {"accountability_style": "default"}"""
    result = _call(system, raw)
    if result and result.get("accountability_style"):
        return result
    return None


def parse_nudge_time(raw: str) -> dict | None:
    system = """Extract a time and convert it to 24-hour format string HH:MM. Respond ONLY with valid JSON, nothing else.
{"nudge_time": "HH:MM or null"}
Examples:
"8pm" -> {"nudge_time": "20:00"}
"20:00" -> {"nudge_time": "20:00"}
"9 in the morning" -> {"nudge_time": "09:00"}
"half 7 at night" -> {"nudge_time": "19:30"}
"10am" -> {"nudge_time": "10:00"}
"9:30pm" -> {"nudge_time": "21:30"}
"noon" -> {"nudge_time": "12:00"}
If you cannot parse a valid time, return {"nudge_time": null}."""
    result = _call(system, raw)
    if result and result.get("nudge_time"):
        return result
    return None


def generate_summary(user_data: dict) -> str:
    """Generate a personalised 2-3 line profile summary in Koda's voice."""
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
    intl_note = " (international student)" if is_international else ""

    prompt = (
        f"Write a 2-3 line summary of {name}'s situation in Koda's voice. "
        f"Direct, lowercase, specific to their profile. Each thought on its own line. "
        f"No fluff. Reference their actual target companies or weak areas. "
        f"End with a line that naturally opens the conversation about their anchor project.\n\n"
        f"Profile:\n"
        f"- Target: {target_type}{intl_note}\n"
        f"- Companies: {companies_str}\n"
        f"- Industry: {industry}\n"
        f"- Experience: {experience}\n"
        f"- LeetCode: {leetcode}\n"
        f"- Weak areas: {weak_str}"
    )

    try:
        response = _client.messages.create(
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
