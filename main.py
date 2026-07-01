import os
import sys
import logging
from typing import Optional
from bot import GitHubFollowBot, BotConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MODES         = frozenset({"follow", "unfollow"})
VALID_SOURCES       = frozenset({"cache", "api"})
TOKEN_MIN_LENGTH    = 20
DAILY_LIMIT_WARNING = 400
MIN_DELAY_WARNING   = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mask_token(token: str) -> str:
    """Safe logging සඳහා token mask කරයි."""
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def validate_token(token: str) -> bool:
    """GitHub token format සහ minimum length validate කරයි."""
    if not token or len(token) < TOKEN_MIN_LENGTH:
        return False
    valid_prefixes = (
        "ghp_",
        "gho_",
        "ghu_",
        "ghs_",
        "ghr_",
        "github_pat_",
    )
    return any(token.startswith(p) for p in valid_prefixes)


def get_env_int(key: str, default: int) -> int:
    """Empty string safe integer conversion."""
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            f"⚠️  Invalid value for {key}: '{raw}'. "
            f"Using default: {default}"
        )
        return default


def get_env_start_page() -> Optional[int]:
    """
    START_PAGE env var read කරයි.
    Set නැත්නම් None return කරයි → auto-resume mode.
    Set කළොත් manual override.
    """
    raw = os.getenv("START_PAGE", "").strip()
    if not raw:
        return None
    try:
        page = int(raw)
        if page < 1:
            logger.warning(
                f"⚠️  START_PAGE must be >= 1, got {page}. "
                f"Using auto-resume."
            )
            return None
        return page
    except ValueError:
        logger.warning(
            f"⚠️  Invalid START_PAGE: '{raw}'. Using auto-resume."
        )
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_config(
    mode:               str,
    unfollow_source:    str,
    min_delay:          int,
    max_delay:          int,
    unfollow_min_delay: int,
    unfollow_max_delay: int,
    follow_limit:       int,
    daily_limit:        int,
) -> list[str]:
    """Configuration validate කර error list return කරයි."""
    errors = []

    if mode not in VALID_MODES:
        errors.append(
            f"BOT_MODE must be one of {sorted(VALID_MODES)}, "
            f"got: '{mode}'"
        )

    if unfollow_source not in VALID_SOURCES:
        errors.append(
            f"UNFOLLOW_SOURCE must be one of {sorted(VALID_SOURCES)}, "
            f"got: '{unfollow_source}'"
        )

    if min_delay >= max_delay:
        errors.append(
            f"MIN_DELAY ({min_delay}) must be < MAX_DELAY ({max_delay})"
        )

    if unfollow_min_delay >= unfollow_max_delay:
        errors.append(
            f"UNFOLLOW_MIN_DELAY ({unfollow_min_delay}) must be "
            f"< UNFOLLOW_MAX_DELAY ({unfollow_max_delay})"
        )

    if follow_limit > daily_limit:
        errors.append(
            f"FOLLOW_LIMIT ({follow_limit}) cannot exceed "
            f"DAILY_LIMIT ({daily_limit})"
        )

    # Non-fatal warnings
    if daily_limit > DAILY_LIMIT_WARNING:
        logger.warning(
            f"⚠️  DAILY_LIMIT={daily_limit} > {DAILY_LIMIT_WARNING} "
            f"risks GitHub account suspension"
        )

    if min_delay < MIN_DELAY_WARNING:
        logger.warning(
            f"⚠️  MIN_DELAY={min_delay}s < {MIN_DELAY_WARNING}s "
            f"may trigger GitHub abuse detection"
        )

    return errors


# ---------------------------------------------------------------------------
# Exit Codes
# ---------------------------------------------------------------------------

class ExitCode:
    SUCCESS          = 0
    AUTH_ERROR       = 1
    NETWORK_ERROR    = 2
    UNEXPECTED_ERROR = 3
    CONFIG_ERROR     = 4
    NO_ACTION        = 5


def evaluate_results(mode: str, results: dict) -> int:
    """Bot results ඉදලා exit code determine කරයි."""
    if mode == "follow":
        actioned = results.get("session_followed",  0)
    else:
        actioned = results.get("session_unfollowed", 0)

    if actioned == 0:
        remaining = (
            results.get("remaining_follows",  0)
            if mode == "follow"
            else results.get("remaining_unfollows", 0)
        )
        if remaining == 0:
            logger.warning("⚠️  Daily limit was already reached")
        else:
            logger.warning("⚠️  No users were actioned this session")
        return ExitCode.NO_ACTION

    return ExitCode.SUCCESS


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _log_startup(
    token:          str,
    mode:           str,
    target_user:    str,
    daily_limit:    int,
    follow_limit:   int,
    start_page:     Optional[int],
    min_delay:      int,
    max_delay:      int,
) -> None:
    logger.info("=" * 55)
    logger.info("⚙️  Configuration")
    logger.info("=" * 55)
    logger.info(f"  🔑 Token         : {mask_token(token)}")
    logger.info(f"  🎯 Mode          : {mode}")
    logger.info(f"  🎯 Target        : {target_user}")
    logger.info(f"  📊 Daily limit   : {daily_limit}")
    logger.info(f"  📊 Session limit : {follow_limit}")
    logger.info(
        f"  📄 Start page    : "
        f"{'auto-resume' if start_page is None else start_page}"
    )
    logger.info(f"  ⏱️  Delay         : {min_delay}s - {max_delay}s")
    logger.info("=" * 55)


def main() -> int:
    logger.info("🚀 GitHub Follow Bot - Starting up")

    # -------------------------------------------------------------------------
    # Environment variables load
    # -------------------------------------------------------------------------
    token           = os.getenv("GITHUB_TOKEN", "").strip()
    target_user     = os.getenv("TARGET_USERNAME", "torvalds").strip()
    mode            = os.getenv("BOT_MODE", "follow").strip().lower()
    unfollow_source = os.getenv("UNFOLLOW_SOURCE", "cache").strip().lower()

    daily_limit          = get_env_int("DAILY_LIMIT",          300)
    follow_limit         = get_env_int("FOLLOW_LIMIT",          50)
    min_delay            = get_env_int("MIN_DELAY",             30)
    max_delay            = get_env_int("MAX_DELAY",             60)
    daily_unfollow_limit = get_env_int("DAILY_UNFOLLOW_LIMIT", 300)
    unfollow_limit       = get_env_int("UNFOLLOW_LIMIT",        50)
    unfollow_min_delay   = get_env_int("UNFOLLOW_MIN_DELAY",    30)
    unfollow_max_delay   = get_env_int("UNFOLLOW_MAX_DELAY",    60)

    # None = auto-resume | int = manual override
    start_page: Optional[int] = get_env_start_page()

    # -------------------------------------------------------------------------
    # Token validation
    # -------------------------------------------------------------------------
    if not token:
        logger.error("❌ GITHUB_TOKEN is not set!")
        return ExitCode.AUTH_ERROR

    if not validate_token(token):
        logger.error(
            f"❌ Invalid token format: {mask_token(token)}. "
            f"Expected: ghp_*, gho_*, ghu_*, ghs_*, ghr_*, github_pat_*"
        )
        return ExitCode.AUTH_ERROR

    # -------------------------------------------------------------------------
    # Config validation
    # -------------------------------------------------------------------------
    errors = validate_config(
        mode               = mode,
        unfollow_source    = unfollow_source,
        min_delay          = min_delay,
        max_delay          = max_delay,
        unfollow_min_delay = unfollow_min_delay,
        unfollow_max_delay = unfollow_max_delay,
        follow_limit       = follow_limit,
        daily_limit        = daily_limit,
    )

    if errors:
        for error in errors:
            logger.error(f"❌ Config error: {error}")
        return ExitCode.CONFIG_ERROR

    # -------------------------------------------------------------------------
    # Startup log
    # -------------------------------------------------------------------------
    _log_startup(
        token        = token,
        mode         = mode,
        target_user  = target_user,
        daily_limit  = daily_limit,
        follow_limit = follow_limit,
        start_page   = start_page,
        min_delay    = min_delay,
        max_delay    = max_delay,
    )

    # -------------------------------------------------------------------------
    # Bot run
    # -------------------------------------------------------------------------
    config = BotConfig(
        daily_follow_limit   = daily_limit,
        follow_limit         = follow_limit,
        min_delay            = min_delay,
        max_delay            = max_delay,
        max_pages            = 40,
        per_page             = 100,
        daily_unfollow_limit = daily_unfollow_limit,
        unfollow_limit       = unfollow_limit,
        unfollow_min_delay   = unfollow_min_delay,
        unfollow_max_delay   = unfollow_max_delay,
    )

    try:
        bot     = GitHubFollowBot(token=token, config=config)
        results: dict

        if mode == "unfollow":
            logger.info("🔄 Running in UNFOLLOW mode")
            results = bot.run_unfollow(
                limit      = unfollow_limit,
                from_cache = (unfollow_source == "cache"),
            )
        else:
            logger.info("➕ Running in FOLLOW mode")
            results = bot.run(
                target_username = target_user,
                limit           = follow_limit,
                start_page      = start_page,
            )

        return evaluate_results(mode, results)

    except PermissionError as e:
        logger.error(f"❌ Authentication failed: {e}")
        return ExitCode.AUTH_ERROR
    except ConnectionError as e:
        logger.error(f"❌ Network error: {e}")
        return ExitCode.NETWORK_ERROR
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user - exiting cleanly")
        return ExitCode.NO_ACTION
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return ExitCode.UNEXPECTED_ERROR


if __name__ == "__main__":
    sys.exit(main())
