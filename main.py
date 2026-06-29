import os
import sys
import logging
from bot import GitHubFollowBot, BotConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def validate_token(token: str) -> bool:
    valid_prefixes = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_")
    return any(token.startswith(prefix) for prefix in valid_prefixes)


def get_env_int(key: str, default: int) -> int:
    """Empty string safe int conversion"""
    value = os.getenv(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(
            f"⚠️  Invalid value for {key}: '{value}'. "
            f"Using default: {default}"
        )
        return default


def main() -> int:
    logger.info("🚀 GitHub Follow Bot - Starting up")

    token           = os.getenv("GITHUB_TOKEN")
    target_user     = os.getenv("TARGET_USERNAME", "torvalds")
    mode            = os.getenv("BOT_MODE", "follow")
    unfollow_source = os.getenv("UNFOLLOW_SOURCE", "cache")

    daily_limit          = get_env_int("DAILY_LIMIT",          300)
    follow_limit         = get_env_int("FOLLOW_LIMIT",          50)
    min_delay            = get_env_int("MIN_DELAY",             30)
    max_delay            = get_env_int("MAX_DELAY",             60)
    daily_unfollow_limit = get_env_int("DAILY_UNFOLLOW_LIMIT", 300)
    unfollow_limit       = get_env_int("UNFOLLOW_LIMIT",        50)
    unfollow_min_delay   = get_env_int("UNFOLLOW_MIN_DELAY",    30)
    unfollow_max_delay   = get_env_int("UNFOLLOW_MAX_DELAY",    60)

    # Fix: Start page - දැනටමත් follow කළ pages skip
    start_page = get_env_int("START_PAGE", 1)

    if not token:
        logger.error("❌ GITHUB_TOKEN not set!")
        return 1

    if not validate_token(token):
        logger.error("❌ Invalid token format.")
        return 1

    logger.info(f"🎯 Mode         : {mode}")
    logger.info(f"🎯 Target       : {target_user}")
    logger.info(f"📊 Daily limit  : {daily_limit}")
    logger.info(f"📊 Session limit: {follow_limit}")
    logger.info(f"📄 Start page   : {start_page}")
    logger.info(f"⏱️  Delay        : {min_delay}s - {max_delay}s")

    config = BotConfig(
        daily_follow_limit=daily_limit,
        follow_limit=follow_limit,
        min_delay=min_delay,
        max_delay=max_delay,
        max_pages=40,
        per_page=100,
        daily_unfollow_limit=daily_unfollow_limit,
        unfollow_limit=unfollow_limit,
        unfollow_min_delay=unfollow_min_delay,
        unfollow_max_delay=unfollow_max_delay,
        start_page=start_page
    )

    try:
        bot = GitHubFollowBot(token=token, config=config)

        if mode == "unfollow":
            logger.info("🔄 Running in UNFOLLOW mode")
            results = bot.run_unfollow(
                limit=unfollow_limit,
                from_cache=(unfollow_source == "cache")
            )
        else:
            logger.info("➕ Running in FOLLOW mode")
            results = bot.run(
                target_username=target_user,
                limit=follow_limit,
                start_page=start_page
            )

        logger.info("✅ Bot completed successfully")
        return 0

    except PermissionError as e:
        logger.error(f"❌ Authentication failed: {e}")
        return 1
    except ConnectionError as e:
        logger.error(f"❌ Network error: {e}")
        return 2
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return 3


if __name__ == "__main__":
    sys.exit(main())
