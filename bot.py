import requests
import time
import random
import os
import json
import logging
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    daily_follow_limit: int = 300
    follow_limit: int = 50
    min_delay: int = 30
    max_delay: int = 60
    rate_limit_threshold: int = 50
    max_pages: int = 40
    per_page: int = 100
    daily_unfollow_limit: int = 300
    unfollow_limit: int = 50
    unfollow_min_delay: int = 30
    unfollow_max_delay: int = 60


@dataclass
class BotStats:
    followed_today: int = 0
    failed_today: int = 0
    total_requests: int = 0
    unfollowed_today: int = 0
    unfollow_failed_today: int = 0
    last_run_date: str = field(
        default_factory=lambda: date.today().isoformat()
    )


class RateLimitError(Exception):
    pass


class GitHubFollowBot:

    STATS_FILE = "bot_stats.json"
    FOLLOWING_CACHE_FILE = "following_cache.json"

    def __init__(self, token: str, config: Optional[BotConfig] = None):
        if not token:
            raise ValueError("GitHub token required")

        self.token = token
        self.config = config or BotConfig()
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Follow-Bot/1.0"
        }

        self.session_start = datetime.now().isoformat()
        self.stats = self._load_stats()
        self._check_daily_reset()

    # -------------------------------------------------------------------------
    # Stats Management
    # -------------------------------------------------------------------------

    def _load_stats(self) -> BotStats:
        try:
            if os.path.exists(self.STATS_FILE):
                with open(self.STATS_FILE, "r") as f:
                    data = json.load(f)
                    data.pop("session_start", None)
                    valid_keys = BotStats.__dataclass_fields__.keys()
                    filtered = {
                        k: v for k, v in data.items()
                        if k in valid_keys
                    }
                    return BotStats(**filtered)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Stats file error: {e}. Starting fresh.")
        return BotStats()

    def _save_stats(self) -> None:
        try:
            with open(self.STATS_FILE, "w") as f:
                json.dump(self.stats.__dict__, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save stats: {e}")

    def _check_daily_reset(self) -> None:
        today = date.today().isoformat()
        if self.stats.last_run_date != today:
            logger.info(
                f"📅 New day detected. Resetting daily stats. "
                f"(Previous: {self.stats.last_run_date})"
            )
            self.stats.followed_today = 0
            self.stats.failed_today = 0
            self.stats.total_requests = 0
            self.stats.unfollowed_today = 0
            self.stats.unfollow_failed_today = 0
            self.stats.last_run_date = today
            self._save_stats()

    # -------------------------------------------------------------------------
    # Following Cache Management
    # -------------------------------------------------------------------------

    def _load_following_cache(self) -> list[str]:
        try:
            if os.path.exists(self.FOLLOWING_CACHE_FILE):
                with open(self.FOLLOWING_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("following", [])
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Cache file error: {e}")
        return []

    def _save_following_cache(self, following: list[str]) -> None:
        try:
            with open(self.FOLLOWING_CACHE_FILE, "w") as f:
                json.dump(
                    {
                        "following": following,
                        "updated_at": datetime.now().isoformat(),
                        "count": len(following)
                    },
                    f,
                    indent=2
                )
        except IOError as e:
            logger.error(f"Failed to save following cache: {e}")

    def _add_to_cache(self, username: str) -> None:
        following = self._load_following_cache()
        if username not in following:
            following.append(username)
            self._save_following_cache(following)

    def _remove_from_cache(self, username: str) -> None:
        following = self._load_following_cache()
        if username in following:
            following.remove(username)
            self._save_following_cache(following)

    # -------------------------------------------------------------------------
    # Rate Limit Handling
    # -------------------------------------------------------------------------

    def _handle_rate_limit(self, response: requests.Response) -> None:
        remaining = int(
            response.headers.get("X-RateLimit-Remaining", 100)
        )
        reset_timestamp = int(
            response.headers.get("X-RateLimit-Reset", 0)
        )

        if remaining <= 1:
            raise RateLimitError(
                f"Rate limit exhausted. "
                f"Resets at: {datetime.fromtimestamp(reset_timestamp)}"
            )

        if remaining < self.config.rate_limit_threshold:
            wait_seconds = max(0, reset_timestamp - time.time())
            logger.warning(
                f"⚠️  Rate limit low: {remaining} remaining. "
                f"Waiting {wait_seconds:.0f}s"
            )
            time.sleep(wait_seconds + 5)

    def _random_delay(self, min_d: int, max_d: int) -> None:
        delay = random.randint(min_d, max_d)
        logger.info(f"⏳ Waiting {delay} seconds...")
        time.sleep(delay)

    # -------------------------------------------------------------------------
    # API Requests
    # -------------------------------------------------------------------------

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=30,
                **kwargs
            )

            self.stats.total_requests += 1

            if method.upper() in ("GET", "PUT", "DELETE"):
                self._handle_rate_limit(response)

            if response.status_code == 401:
                raise PermissionError("❌ Invalid token.")
            elif response.status_code == 403:
                raise RateLimitError("❌ Forbidden.")
            elif response.status_code == 404:
                raise ValueError(f"❌ Not found: {url}")
            elif response.status_code == 422:
                raise ValueError("❌ Unprocessable Entity.")

            if response.status_code not in (200, 204):
                response.raise_for_status()

            return response

        except requests.exceptions.ConnectionError:
            raise ConnectionError("❌ Network error.")
        except requests.exceptions.Timeout:
            raise TimeoutError("❌ Request timed out.")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"❌ Request failed: {e}")

    # -------------------------------------------------------------------------
    # Core Functions
    # -------------------------------------------------------------------------

    def get_followers_with_pagination(
        self,
        username: str,
        needed: int
    ) -> list[str]:
        """
        Fix: needed × 3 buffer fetch කිරීම
        Already following users account කිරීමට
        """
        all_followers = []
        page = 1

        # Fix: needed × 3 buffer
        # Already following ~80% assume කිරීම
        fetch_target = min(needed * 3, 3000)

        logger.info(
            f"📋 Fetching followers for: {username} "
            f"(need ~{needed}, fetching up to {fetch_target})"
        )

        while page <= self.config.max_pages:
            url = (
                f"{self.base_url}/users/{username}/followers"
                f"?per_page={self.config.per_page}&page={page}"
            )

            try:
                response = self._make_request("GET", url)
                followers_page = response.json()

                if not followers_page:
                    logger.info(
                        f"✅ All pages fetched. "
                        f"Total: {len(all_followers)}"
                    )
                    break

                usernames = [u["login"] for u in followers_page]
                all_followers.extend(usernames)

                logger.info(
                    f"  📄 Page {page}: {len(usernames)} followers "
                    f"(Total: {len(all_followers)}/{fetch_target})"
                )

                # Fix: fetch_target දක්වා fetch කිරීම
                if len(all_followers) >= fetch_target:
                    logger.info(
                        f"✅ Fetched {fetch_target} users. Stopping."
                    )
                    break

                page += 1
                time.sleep(random.uniform(1, 3))

            except (RateLimitError, PermissionError) as e:
                logger.error(f"Critical error: {e}")
                break
            except Exception as e:
                logger.warning(f"Page {page} error: {e}")
                break

        return all_followers

    def get_my_following(self, limit: int = 300) -> list[str]:
        all_following = []
        page = 1

        logger.info("📋 Fetching your following list...")

        while page <= self.config.max_pages:
            url = (
                f"{self.base_url}/user/following"
                f"?per_page={self.config.per_page}&page={page}"
            )

            try:
                response = self._make_request("GET", url)
                following_page = response.json()

                if not following_page:
                    break

                usernames = [u["login"] for u in following_page]
                all_following.extend(usernames)

                logger.info(
                    f"  📄 Page {page}: {len(usernames)} following "
                    f"(Total: {len(all_following)})"
                )

                if len(all_following) >= limit:
                    break

                page += 1
                time.sleep(random.uniform(1, 3))

            except (RateLimitError, PermissionError) as e:
                logger.error(f"Critical error: {e}")
                break
            except Exception as e:
                logger.warning(f"Page {page} error: {e}")
                break

        return all_following

    def check_already_following(self, username: str) -> bool:
        url = f"{self.base_url}/user/following/{username}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=30
            )
            self.stats.total_requests += 1

            if response.status_code == 204:
                return True
            if response.status_code == 404:
                return False
            if response.status_code == 401:
                raise PermissionError("Invalid token")

            return False

        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Could not check {username}: {e}")
            return False

    def follow_user(self, username: str) -> bool:
        if self.stats.followed_today >= self.config.daily_follow_limit:
            logger.warning(
                f"🛑 Daily follow limit reached: "
                f"{self.stats.followed_today}/"
                f"{self.config.daily_follow_limit}"
            )
            return False

        url = f"{self.base_url}/user/following/{username}"

        try:
            response = self._make_request("PUT", url)

            if response.status_code == 204:
                self.stats.followed_today += 1
                self._save_stats()
                self._add_to_cache(username)
                return True

            return False

        except (PermissionError, RateLimitError) as e:
            logger.error(f"Cannot follow {username}: {e}")
            self.stats.failed_today += 1
            self._save_stats()
            return False
        except Exception as e:
            logger.warning(f"Failed to follow {username}: {e}")
            self.stats.failed_today += 1
            self._save_stats()
            return False

    def unfollow_user(self, username: str) -> bool:
        if self.stats.unfollowed_today >= self.config.daily_unfollow_limit:
            logger.warning(
                f"🛑 Daily unfollow limit reached: "
                f"{self.stats.unfollowed_today}/"
                f"{self.config.daily_unfollow_limit}"
            )
            return False

        url = f"{self.base_url}/user/following/{username}"

        try:
            response = self._make_request("DELETE", url)

            if response.status_code == 204:
                self.stats.unfollowed_today += 1
                self._save_stats()
                self._remove_from_cache(username)
                return True

            return False

        except (PermissionError, RateLimitError) as e:
            logger.error(f"Cannot unfollow {username}: {e}")
            self.stats.unfollow_failed_today += 1
            self._save_stats()
            return False
        except Exception as e:
            logger.warning(f"Failed to unfollow {username}: {e}")
            self.stats.unfollow_failed_today += 1
            self._save_stats()
            return False

    # -------------------------------------------------------------------------
    # Main Bot Flows
    # -------------------------------------------------------------------------

    def run(
        self,
        target_username: str,
        limit: Optional[int] = None
    ) -> dict:
        remaining_daily = (
            self.config.daily_follow_limit - self.stats.followed_today
        )

        if remaining_daily <= 0:
            logger.warning("🛑 Daily follow limit already reached.")
            return self._get_session_summary()

        effective_limit = min(
            limit or self.config.follow_limit,
            remaining_daily
        )

        logger.info("=" * 50)
        logger.info("🤖 GitHub Follow Bot Starting")
        logger.info(f"🎯 Target: {target_username}")
        logger.info(f"📊 Will follow up to: {effective_limit} users")
        logger.info(
            f"📅 Today's progress: "
            f"{self.stats.followed_today}/"
            f"{self.config.daily_follow_limit}"
        )
        logger.info(f"🕐 Session start: {self.session_start}")
        logger.info("=" * 50)

        followers = self.get_followers_with_pagination(
            target_username,
            needed=effective_limit
        )

        if not followers:
            logger.error(f"No followers found for {target_username}")
            return self._get_session_summary()

        logger.info(
            f"\n🚀 Starting to follow {effective_limit} users...\n"
        )

        session_followed = 0
        session_skipped = 0

        for username in followers:
            if self.stats.followed_today >= self.config.daily_follow_limit:
                logger.warning("🛑 Daily limit reached.")
                break

            if session_followed >= effective_limit:
                logger.info(f"✅ Session limit: {effective_limit}")
                break

            if self.check_already_following(username):
                logger.info(f"⏭️  Already following: {username}")
                session_skipped += 1
                continue

            if self.follow_user(username):
                logger.info(
                    f"✅ Followed: {username} "
                    f"({self.stats.followed_today}/"
                    f"{self.config.daily_follow_limit} today)"
                )
                session_followed += 1
            else:
                logger.warning(f"❌ Failed: {username}")

            self._random_delay(
                self.config.min_delay,
                self.config.max_delay
            )

        return self._get_session_summary(session_followed, session_skipped)

    def run_unfollow(
        self,
        limit: Optional[int] = None,
        from_cache: bool = True
    ) -> dict:
        remaining_daily = (
            self.config.daily_unfollow_limit - self.stats.unfollowed_today
        )

        if remaining_daily <= 0:
            logger.warning("🛑 Daily unfollow limit already reached.")
            return self._get_session_summary()

        effective_limit = min(
            limit or self.config.unfollow_limit,
            remaining_daily
        )

        logger.info("=" * 50)
        logger.info("🤖 GitHub Unfollow Bot Starting")
        logger.info(f"📊 Will unfollow up to: {effective_limit} users")
        logger.info(
            f"📋 Source: "
            f"{'Bot cache' if from_cache else 'Full following list'}"
        )
        logger.info(
            f"📅 Today's progress: "
            f"{self.stats.unfollowed_today}/"
            f"{self.config.daily_unfollow_limit}"
        )
        logger.info("=" * 50)

        if from_cache:
            to_unfollow = self._load_following_cache()
            logger.info(
                f"📋 Found {len(to_unfollow)} users in bot cache"
            )
        else:
            to_unfollow = self.get_my_following(
                limit=self.config.daily_unfollow_limit
            )
            logger.info(
                f"📋 Found {len(to_unfollow)} users in following list"
            )

        if not to_unfollow:
            logger.warning("⚠️  No users to unfollow")
            return self._get_session_summary()

        logger.info(
            f"\n🚀 Starting to unfollow {effective_limit} users...\n"
        )

        session_unfollowed = 0
        session_failed = 0

        for username in to_unfollow:
            if self.stats.unfollowed_today >= self.config.daily_unfollow_limit:
                logger.warning("🛑 Daily unfollow limit reached.")
                break

            if session_unfollowed >= effective_limit:
                logger.info(
                    f"✅ Session unfollow limit: {effective_limit}"
                )
                break

            if self.unfollow_user(username):
                logger.info(
                    f"✅ Unfollowed: {username} "
                    f"({self.stats.unfollowed_today}/"
                    f"{self.config.daily_unfollow_limit} today)"
                )
                session_unfollowed += 1
            else:
                logger.warning(f"❌ Failed: {username}")
                session_failed += 1

            self._random_delay(
                self.config.unfollow_min_delay,
                self.config.unfollow_max_delay
            )

        return self._get_session_summary(
            unfollowed=session_unfollowed,
            unfollow_failed=session_failed
        )

    def _get_session_summary(
        self,
        followed: int = 0,
        skipped: int = 0,
        unfollowed: int = 0,
        unfollow_failed: int = 0
    ) -> dict:
        summary = {
            "session_followed": followed,
            "session_skipped": skipped,
            "session_unfollowed": unfollowed,
            "session_unfollow_failed": unfollow_failed,
            "followed_today": self.stats.followed_today,
            "unfollowed_today": self.stats.unfollowed_today,
            "failed_today": self.stats.failed_today,
            "total_requests": self.stats.total_requests,
            "daily_follow_limit": self.config.daily_follow_limit,
            "daily_unfollow_limit": self.config.daily_unfollow_limit,
            "remaining_follows": max(
                0,
                self.config.daily_follow_limit - self.stats.followed_today
            ),
            "remaining_unfollows": max(
                0,
                self.config.daily_unfollow_limit - self.stats.unfollowed_today
            ),
            "session_start": self.session_start,
            "session_end": datetime.now().isoformat()
        }

        logger.info("\n" + "=" * 50)
        logger.info("📊 SESSION SUMMARY")
        logger.info("=" * 50)
        for key, value in summary.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 50)

        return summary
