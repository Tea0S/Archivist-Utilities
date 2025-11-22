import os
import re
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Callable, TypeVar, Awaitable, Union
from .config import settings
import discord

log = logging.getLogger(__name__)

T = TypeVar('T')

# ---------- Permission helpers ----------
def is_owner(user: Union[discord.User, discord.Member]) -> bool:
    """
    Check if a user is the bot owner.
    
    Args:
        user: Discord user or member object
        
    Returns:
        True if user is the bot owner, False otherwise
    """
    if not settings.OWNER_ID:
        return False
    return user.id == settings.OWNER_ID

def is_owner_or_admin(user: Union[discord.User, discord.Member]) -> bool:
    """
    Check if a user is the bot owner OR has administrator permissions.
    This allows the owner to bypass permission checks even if they don't have admin perms.
    
    Args:
        user: Discord user or member object (must be a Member for guild_permissions)
        
    Returns:
        True if user is owner or has admin permissions, False otherwise
    """
    # Check if user is owner first (this works for both User and Member)
    if is_owner(user):
        return True
    
    # Check admin permissions (requires Member object with guild_permissions)
    if isinstance(user, discord.Member):
        return user.guild_permissions.administrator
    
    # If it's just a User (not a Member), they can't have guild permissions
    return False

# ---------- Council log ----------
async def log_to_council(bot, msg: str):
    if not settings.COUNCIL_LOG_CHANNEL_ID:
        return
    ch = bot.get_channel(settings.COUNCIL_LOG_CHANNEL_ID)
    if not ch:
        return
    try:
        await ch.send(msg)
    except Exception:
        pass

# ---------- Date/time helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def seconds_until_local(hour_local: int) -> float:
    offset = timedelta(hours=settings.TZ_OFFSET_HOURS)
    local_now = now_utc() + offset
    target = local_now.replace(hour=hour_local, minute=0, second=0, microsecond=0)
    if target <= local_now:
        target += timedelta(days=1)
    return (target - local_now).total_seconds()

DATE_ISO_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
DATE_US_RE  = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")

def parse_date(text: str) -> Optional[datetime]:
    s = (text or "").strip()
    m = DATE_ISO_RE.match(s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = DATE_US_RE.match(s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None

# ---------- Name helpers ----------
PLAYER_PAREN_RE = re.compile(r"\((.*?)\)$")

def nickname_to_player(disp_name: str) -> Optional[str]:
    if not disp_name:
        return None
    m = PLAYER_PAREN_RE.search(disp_name)
    return m.group(1).strip() if m else None

# ---------- Submissions parsing ----------

FIELD_PATTERNS = {
    "name": [
        r"full\s*name",
        r"name",
    ],
    "court": [
        r"court",
    ],
    "title": [
        r"role",  # maps Role -> Title
        r"title",
    ],
    "race": [
        r"race",
    ],
    "gender": [
        r"gender\s*&\s*pronouns",
        r"gender\s*and\s*pronouns",
        r"gender\s*/\s*pronouns",
        r"gender",
    ],
    "sexuality": [
        r"sexuality",
        r"orientation",
    ],
    "age": [
        r"age",
    ],
    "height": [
        r"height",
    ],
}

# Accept markdown, extra asterisks/spaces, and common separators
# e.g. "**Full Name:** Value", "Full Name - Value", "Full Name — Value"
LABEL_RE_FMT = r"""
    ^\s*
    [\*\_~`]*\s*              # open md markers (optional)
    (?P<label>{label})        # label
    [\*\_~`]*\s*              # close md markers (optional)
    [:\-\u2014]\s*            # separator (: or - or —)
    (?P<value>.+?)            # the value (to EOL)
    \s*$
"""

def _compile_label_res():
    comps = {}
    for key, patterns in FIELD_PATTERNS.items():
        compiled = []
        for p in patterns:
            label = r"(?:{p})".format(p=p)
            rx = re.compile(
                LABEL_RE_FMT.format(label=label),
                re.IGNORECASE | re.MULTILINE | re.VERBOSE,
            )
            compiled.append(rx)
        comps[key] = compiled
    return comps

_LABEL_RES = _compile_label_res()

def _strip_md(s: str) -> str:
    s = s or ""
    # Remove surrounding markdown markers
    s = re.sub(r"^\s*[`*_~]+\s*|\s*[`*_~]+\s*$", "", s)
    return s.strip()

def _strip_pronouns(g: str) -> str:
    # "Female (she/her)" -> "Female"
    g = g or ""
    g = re.sub(r"\s*\(.*?\)\s*$", "", g).strip()
    g = re.sub(r"\s*[-•]+\s*$", "", g).strip()
    return g

def _norm_sexuality(s: str) -> str:
    t = (s or "").strip().lower()
    rules = [
        (r"^(hetero|heterosexual|straight)\b", "Straight"),
        (r"^(bi|bisexual)\b", "Bi"),
        (r"^(pan|pansexual)\b", "Pan"),
        (r"^gay\b", "Gay"),
        (r"^lesbian\b", "Lesbian"),
        (r"^(asexual|ace)\b", "Asexual"),
    ]
    for pat, out in rules:
        if re.search(pat, t):
            return out
    return s.strip()

def _find_field(text: str, key: str) -> str | None:
    for rx in _LABEL_RES[key]:
        m = rx.search(text)
        if m:
            return _strip_md(m.group("value"))
    return None

def parse_submission_text(text: str):
    """
    Parse the submission template from free-form Discord text (multi-message safe).
    Returns dict with required fields or None if not enough info yet.
    """
    if not text:
        return None

    # Normalize line endings
    t = text.replace("\r", "")

    # Pull fields with tolerant matching
    name = _find_field(t, "name")
    court = _find_field(t, "court")
    title = _find_field(t, "title")
    race = _find_field(t, "race")
    gender = _find_field(t, "gender")
    sexuality = _find_field(t, "sexuality")
    age = _find_field(t, "age")
    height = _find_field(t, "height")

    # Clean-ups
    if gender:
        gender = _strip_pronouns(gender)
    if sexuality:
        sexuality = _norm_sexuality(sexuality)

    # Require all core fields before we fire the webhook (prevents early partials)
    required = [name, court, title, race, gender, sexuality, age, height]
    if any(v is None or str(v).strip() == "" for v in required):
        return None

    # Hand off to GAS; GAS will also fuzz court and normalize gender/sexuality as a backstop
    return {
        "name": name.strip(),
        "court": court.strip(),
        "title": title.strip(),
        "race": race.strip(),
        "gender": gender.strip(),
        "sexuality": sexuality.strip(),
        "age": age.strip(),
        "height": height.strip(),
    }
# ---------- Snooze store (hiatus) ----------
def load_snooze(path: str) -> Dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_snooze(path: str, d: Dict[str, str]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass

# ---------- Rate limiting helpers for Discord API ----------

async def rate_limit_retry(
    func: Callable[..., Awaitable[T]],
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    *args,
    **kwargs
) -> T:
    """
    Retry a Discord API call with exponential backoff on rate limit errors.
    
    Args:
        func: Async function to call
        max_retries: Maximum number of retries
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay in seconds
        *args, **kwargs: Arguments to pass to func
    
    Returns:
        Result of func
    
    Raises:
        Exception: If all retries are exhausted
    """
    import discord
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                if attempt < max_retries - 1:
                    # Get retry_after from response if available
                    retry_after = getattr(e, 'retry_after', None)
                    if retry_after:
                        delay = min(float(retry_after), max_delay)
                    else:
                        # Exponential backoff: base_delay * 2^attempt
                        delay = min(base_delay * (2 ** attempt), max_delay)
                    
                    log.warning(
                        f"Rate limited (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    log.error(f"Rate limit exceeded after {max_retries} attempts")
                    raise
            else:
                # Not a rate limit error, re-raise immediately
                raise
        except Exception as e:
            # For other exceptions, check if it's a rate limit related error
            error_str = str(e).lower()
            if 'rate limit' in error_str or '429' in error_str:
                if attempt < max_retries - 1:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    log.warning(
                        f"Rate limit detected (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    log.error(f"Rate limit exceeded after {max_retries} attempts")
                    raise
            else:
                # Not a rate limit error, re-raise immediately
                raise
    
    # Should never reach here, but just in case
    raise Exception(f"Failed after {max_retries} attempts")

async def rate_limited_archived_threads(
    forum: 'discord.ForumChannel',
    limit: Optional[int] = None,
    delay_between_pages: float = 0.5
) -> List['discord.Thread']:
    """
    Fetch archived threads with rate limiting protection and delays between pages.
    
    Args:
        forum: Forum channel to fetch from
        limit: Maximum number of threads to fetch (None for all)
        delay_between_pages: Delay in seconds between paginated requests
    
    Returns:
        List of archived threads
    """
    threads = []
    async for thread in forum.archived_threads(limit=limit):
        threads.append(thread)
        # Add a small delay between pages to avoid rate limits
        if delay_between_pages > 0:
            await asyncio.sleep(delay_between_pages)
    return threads

async def rate_limited_message_history(
    channel: Union['discord.TextChannel', 'discord.Thread'],
    limit: Optional[int] = None,
    delay_between_pages: float = 0.3
) -> List['discord.Message']:
    """
    Fetch message history with rate limiting protection and delays between pages.
    
    Args:
        channel: Channel or thread to fetch from
        limit: Maximum number of messages to fetch (None for all)
        delay_between_pages: Delay in seconds between paginated requests
    
    Returns:
        List of messages
    """
    messages = []
    async for message in channel.history(limit=limit):
        messages.append(message)
        # Add a small delay between pages to avoid rate limits
        if delay_between_pages > 0:
            await asyncio.sleep(delay_between_pages)
    return messages