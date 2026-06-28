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


def main() -> int:
    logger.info("🚀 GitHub Follow Bot - Starting up")

    token        = os.getenv("GITHUB_TOKEN")
    target_user  = os.getenv("TARGET_USERNAME", "torvalds")
    daily_limit  = int(os.getenv("DAILY_LIMIT",          "300"))
    follow_limit = int(os.getenv("FOLLOW_LIMIT",          "50"))
    min_delay    = int(os.getenv("MIN_DELAY",             "30"))
    max_delay    = int(os.getenv("MAX_DELAY",             "60"))

    # Unfollow settings
    mode                  = os.getenv("BOT_MODE", "follow")
    daily_unfollow_limit  = int(os.getenv("DAILY_UNFOLLOW_LIMIT", "300"))
    unfollow_limit        = int(os.getenv("UNFOLLOW_LIMIT",        "50"))
    unfollow_min_delay    = int(os.getenv("UNFOLLOW_MIN_DELAY",    "30"))
    unfollow_max_delay    = int(os.getenv("UNFOLLOW_MAX_DELAY",    "60"))
    # cache = bot follow කළ users විතරක් unfollow
    # all   = සම්පූර්ණ following list unfollow
    unfollow_source       = os.getenv("UNFOLLOW_SOURCE", "cache")

    if not token:
        logger.error("❌ GITHUB_TOKEN not set!")
        return 1

    if not validate_token(token):
        logger.error("❌ Invalid token format.")
        return 1

    logger.info(f"🎯 Mode        : {mode}")
    logger.info(f"🎯 Target      : {target_user}")
    logger.info(f"📊 Daily limit : {daily_limit}")
    logger.info(f"📊 Session limit: {follow_limit}")
    logger.info(f"⏱️  Delay       : {min_delay}s - {max_delay}s")

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
        unfollow_max_delay=unfollow_max_delay
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
                limit=follow_limit
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
