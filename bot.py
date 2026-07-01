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
    daily_follow_limit:   int = 300
    follow_limit:         int = 50
    min_delay:            int = 30
    max_delay:            int = 60
    rate_limit_threshold: int = 50
    max_pages:            int = 40
    per_page:             int = 100
    daily_unfollow_limit: int = 300
    unfollow_limit:       int = 50
    unfollow_min_delay:   int = 30
    unfollow_max_delay:   int = 60
    start_page:           int = 1

    def __post_init__(self):
        errors = []

        if not 1 <= self.per_page <= 100:
            errors.append("per_page must be 1-100")

        if self.min_delay >= self.max_delay:
            errors.append(
                f"min_delay ({self.min_delay}) must be "
                f"< max_delay ({self.max_delay})"
            )

        if self.unfollow_min_delay >= self.unfollow_max_delay:
            errors.append(
                f"unfollow_min_delay ({self.unfollow_min_delay}) must be "
                f"< unfollow_max_delay ({self.unfollow_max_delay})"
            )

        if self.start_page < 1:
            errors.append(f"start_page must be >= 1")

        if self.follow_limit > self.daily_follow_limit:
            errors.append(
                f"follow_limit ({self.follow_limit}) cannot exceed "
                f"daily_follow_limit ({self.daily_follow_limit})"
            )

        if errors:
            raise ValueError(f"BotConfig errors: {'; '.join(errors)}")

        if self.daily_follow_limit > 400:
            logger.warning(
                "⚠️  daily_follow_limit > 400 risks account suspension"
            )

        if self.min_delay < 10:
            logger.warning(
                "⚠️  min_delay < 10s may trigger abuse detection"
            )


@dataclass
class BotStats:
    followed_today:       int = 0
    failed_today:         int = 0
    total_requests:       int = 0
    unfollowed_today:     int = 0
    unfollow_failed_today: int = 0
    last_run_date:        str = field(
        default_factory=lambda: date.today().isoformat()
    )


class RateLimitError(Exception):
    pass


class GitHubFollowBot:

    STATS_FILE           = "bot_stats.json"
    FOLLOWING_CACHE_FILE = "following_cache.json"
    PAGINATION_FILE      = "pagination_state.json"

    def __init__(self, token: str, config: Optional[BotConfig] = None):
        if not token or not token.strip():
            raise ValueError("GitHub token required")

        self.config        = config or BotConfig()
        self.base_url      = "https://api.github.com"
        self._headers      = {
            "Authorization": f"token {token}",
            "Accept":        "application/vnd.github.v3+json",
            "User-Agent":    "GitHub-Follow-Bot/1.0"
        }
        self.session_start = datetime.now().isoformat()
        self.stats         = self._load_stats()
        self._check_daily_reset()

    @property
    def headers(self) -> dict:
        return self._headers.copy()

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
                    filtered   = {
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
            self.stats.followed_today        = 0
            self.stats.failed_today          = 0
            self.stats.total_requests        = 0
            self.stats.unfollowed_today      = 0
            self.stats.unfollow_failed_today = 0
            self.stats.last_run_date         = today
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
                        "following":  following,
                        "updated_at": datetime.now().isoformat(),
                        "count":      len(following)
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
    # Pagination State Management
    # -------------------------------------------------------------------------

    def _load_pagination_state(self) -> dict:
        """
        Last successful page number save කරගෙන ඉන්නවා.
        Format: { "username": { "last_page": 5, "updated_at": "..." } }
        """
        try:
            if os.path.exists(self.PAGINATION_FILE):
                with open(self.PAGINATION_FILE, "r") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Pagination state read error: {e}")
        return {}

    def _save_pagination_state(self, username: str, next_page: int) -> None:
        """Target username සඳහා next page save කරයි."""
        state = self._load_pagination_state()
        state[username] = {
            "last_page":  next_page,
            "updated_at": datetime.now().isoformat()
        }
        try:
            with open(self.PAGINATION_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save pagination state: {e}")

    def _get_resume_page(self, username: str) -> int:
        """
        Username සඳහා resume page return කරයි.
        State නැත්නම් config.start_page return කරයි.
        """
        state = self._load_pagination_state()
        if username in state:
            last = state[username]["last_page"]
            logger.info(
                f"📌 Resuming '{username}' from page {last} "
                f"(saved: {state[username]['updated_at']})"
            )
            return last
        return self.config.start_page

    def reset_pagination(self, username: str) -> None:
        """Username සඳහා pagination state reset කරයි."""
        state = self._load_pagination_state()
        if username in state:
            del state[username]
            try:
                with open(self.PAGINATION_FILE, "w") as f:
                    json.dump(state, f, indent=2)
                logger.info(
                    f"🔄 Pagination reset for '{username}'. "
                    f"Next run starts from page 1."
                )
            except IOError as e:
                logger.error(f"Failed to reset pagination: {e}")

    # -------------------------------------------------------------------------
    # Rate Limit Handling
    # -------------------------------------------------------------------------

    def _handle_rate_limit(self, response: requests.Response) -> None:
        remaining       = int(
            response.headers.get("X-RateLimit-Remaining", 100)
        )
        reset_timestamp = int(
            response.headers.get("X-RateLimit-Reset", 0)
        )

        if remaining == 0:
            wait_seconds = max(0, reset_timestamp - time.time())
            raise RateLimitError(
                f"Rate limit exhausted. "
                f"Resets in {wait_seconds:.0f}s "
                f"at {datetime.fromtimestamp(reset_timestamp)}"
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
        url:    str,
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
            self._handle_rate_limit(response)

            if response.status_code == 401:
                raise PermissionError("Invalid or expired token")
            elif response.status_code == 403:
                body = {}
                try:
                    body = response.json()
                except Exception:
                    pass
                if "rate limit" in body.get("message", "").lower():
                    raise RateLimitError("Rate limit hit via 403")
                raise PermissionError(
                    f"Forbidden: {body.get('message', 'No message')}"
                )
            elif response.status_code == 404:
                raise ValueError(f"Not found: {url}")
            elif response.status_code == 422:
                raise ValueError("Unprocessable Entity")

            if response.status_code not in (200, 204):
                response.raise_for_status()

            return response

        except requests.exceptions.ConnectionError:
            raise ConnectionError("Network error - check your connection")
        except requests.exceptions.Timeout:
            raise TimeoutError("Request timed out after 30s")
        except (PermissionError, RateLimitError, ValueError):
            raise
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request failed: {e}")

    # -------------------------------------------------------------------------
    # Core API Functions
    # -------------------------------------------------------------------------

    def get_followers_with_pagination(
        self,
        username:   str,
        needed:     int,
        start_page: Optional[int] = None
    ) -> list[str]:
        """
        Fresh (follow නොකළ) users needed count එකට හම්බ වෙනතුරු fetch කරයි.

        start_page:
          - None  → pagination_state.json ඉදලා auto-resume
          - int   → manual override (pagination state ignore කරයි)

        Page state persist කරයි - crash වුනොත් resume කළ හැකිය.
        Followers ඉවර වුනොත් pagination reset කර page 1 ඉදලා restart.
        """
        # Auto-resume හෝ manual override
        if start_page is None:
            current_page = self._get_resume_page(username)
        else:
            current_page = start_page
            logger.info(f"📄 Manual start page override: {current_page}")

        # Already following set - O(1) lookup සඳහා
        already_following_set = set(self._load_following_cache())

        fresh_users = []
        max_page    = current_page + self.config.max_pages

        logger.info(
            f"📋 Fetching fresh followers | "
            f"Target: {username} | "
            f"Need: {needed} | "
            f"From page: {current_page} | "
            f"Cache: {len(already_following_set)} users"
        )

        while current_page <= max_page:
            url = (
                f"{self.base_url}/users/{username}/followers"
                f"?per_page={self.config.per_page}&page={current_page}"
            )

            try:
                response  = self._make_request("GET", url)
                page_data = response.json()

                # Empty page = followers ඉවරයි
                if not page_data:
                    logger.info(
                        f"📭 No more followers at page {current_page}. "
                        f"Resetting pagination for next run."
                    )
                    self.reset_pagination(username)
                    break

                page_users    = [u["login"] for u in page_data]
                fresh_on_page = [
                    u for u in page_users
                    if u not in already_following_set
                ]
                skipped       = len(page_users) - len(fresh_on_page)

                fresh_users.extend(fresh_on_page)

                logger.info(
                    f"  📄 Page {current_page}: "
                    f"{len(page_users)} total | "
                    f"✅ {len(fresh_on_page)} fresh | "
                    f"⏭️  {skipped} skip | "
                    f"📦 {len(fresh_users)} accumulated"
                )

                # Next page state save - crash recovery සඳහා
                self._save_pagination_state(username, current_page + 1)

                # Enough fresh users ලැබුණාද?
                if len(fresh_users) >= needed:
                    logger.info(
                        f"✅ Found enough fresh users: "
                        f"{len(fresh_users)} >= {needed}"
                    )
                    break

                current_page += 1
                time.sleep(random.uniform(1, 3))

            except (RateLimitError, PermissionError) as e:
                logger.error(
                    f"❌ Critical error at page {current_page}: {e}"
                )
                break
            except Exception as e:
                logger.warning(
                    f"⚠️  Page {current_page} error: {e}"
                )
                break

        logger.info(
            f"📊 Fetch complete: {len(fresh_users)} fresh users ready"
        )
        return fresh_users

    def get_my_following(self, limit: int = 300) -> list[str]:
        all_following = []
        page          = 1

        logger.info("📋 Fetching your following list...")

        while page <= self.config.max_pages:
            url = (
                f"{self.base_url}/user/following"
                f"?per_page={self.config.per_page}&page={page}"
            )

            try:
                response       = self._make_request("GET", url)
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
        """Cache hit නම් API call skip කරයි."""
        # Cache check first - API call avoid කිරීමට
        cache = set(self._load_following_cache())
        if username in cache:
            return True

        # Cache miss - API verify
        url = f"{self.base_url}/user/following/{username}"

        try:
            response = self._make_request("GET", url)
            return response.status_code == 204

        except ValueError:
            # 404 = not following
            return False
        except (PermissionError, RateLimitError):
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
            raise
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
            raise
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
        limit:           Optional[int] = None,
        start_page:      Optional[int] = None
    ) -> dict:
        """
        start_page:
          - None → auto-resume from pagination_state.json
          - int  → manual page override
        """
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

        logger.info("=" * 55)
        logger.info("🤖 GitHub Follow Bot Starting")
        logger.info(f"   🎯 Target       : {target_username}")
        logger.info(f"   📊 Session goal : {effective_limit} follows")
        logger.info(
            f"   📄 Page mode    : "
            f"{'auto-resume' if start_page is None else f'page {start_page}'}"
        )
        logger.info(
            f"   📅 Today        : "
            f"{self.stats.followed_today}/{self.config.daily_follow_limit}"
        )
        logger.info(f"   🕐 Session start: {self.session_start}")
        logger.info("=" * 55)

        # Fresh users மட்டும் fetch - already following skip
        fresh_followers = self.get_followers_with_pagination(
            username   = target_username,
            needed     = effective_limit,
            start_page = start_page
        )

        if not fresh_followers:
            logger.warning(
                f"⚠️  No fresh users found for '{target_username}'. "
                f"All reachable pages may be exhausted."
            )
            return self._get_session_summary()

        logger.info(
            f"\n🚀 Starting to follow "
            f"{min(len(fresh_followers), effective_limit)} "
            f"fresh users...\n"
        )

        session_followed = 0
        session_skipped  = 0

        for username in fresh_followers:
            # Daily limit check
            if self.stats.followed_today >= self.config.daily_follow_limit:
                logger.warning("🛑 Daily limit reached mid-session.")
                break

            # Session limit check
            if session_followed >= effective_limit:
                logger.info(
                    f"✅ Session goal reached: "
                    f"{session_followed}/{effective_limit}"
                )
                break

            # Double-check (cache miss edge case)
            if self.check_already_following(username):
                logger.info(f"⏭️  Double-check skip: {username}")
                session_skipped += 1
                continue

            if self.follow_user(username):
                logger.info(
                    f"✅ [{session_followed + 1}/{effective_limit}] "
                    f"Followed: {username} "
                    f"({self.stats.followed_today}/"
                    f"{self.config.daily_follow_limit} today)"
                )
                session_followed += 1

                # Last user නම් delay skip
                if session_followed < effective_limit:
                    self._random_delay(
                        self.config.min_delay,
                        self.config.max_delay
                    )
            else:
                logger.warning(f"❌ Failed: {username}")

        return self._get_session_summary(session_followed, session_skipped)

    def run_unfollow(
        self,
        limit:      Optional[int] = None,
        from_cache: bool          = True
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

        logger.info("=" * 55)
        logger.info("🤖 GitHub Unfollow Bot Starting")
        logger.info(f"   📊 Session goal : {effective_limit} unfollows")
        logger.info(
            f"   📋 Source       : "
            f"{'Bot cache' if from_cache else 'API (full list)'}"
        )
        logger.info(
            f"   📅 Today        : "
            f"{self.stats.unfollowed_today}/"
            f"{self.config.daily_unfollow_limit}"
        )
        logger.info("=" * 55)

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
                f"📋 Found {len(to_unfollow)} users via API"
            )

        if not to_unfollow:
            logger.warning("⚠️  No users to unfollow")
            return self._get_session_summary()

        logger.info(
            f"\n🚀 Starting to unfollow up to {effective_limit} users...\n"
        )

        session_unfollowed = 0
        session_failed     = 0

        for username in to_unfollow:
            if self.stats.unfollowed_today >= self.config.daily_unfollow_limit:
                logger.warning("🛑 Daily unfollow limit reached.")
                break

            if session_unfollowed >= effective_limit:
                logger.info(
                    f"✅ Session goal reached: "
                    f"{session_unfollowed}/{effective_limit}"
                )
                break

            if self.unfollow_user(username):
                logger.info(
                    f"✅ [{session_unfollowed + 1}/{effective_limit}] "
                    f"Unfollowed: {username} "
                    f"({self.stats.unfollowed_today}/"
                    f"{self.config.daily_unfollow_limit} today)"
                )
                session_unfollowed += 1

                if session_unfollowed < effective_limit:
                    self._random_delay(
                        self.config.unfollow_min_delay,
                        self.config.unfollow_max_delay
                    )
            else:
                logger.warning(f"❌ Failed: {username}")
                session_failed += 1

        return self._get_session_summary(
            unfollowed     = session_unfollowed,
            unfollow_failed = session_failed
        )

    def _get_session_summary(
        self,
        followed:        int = 0,
        skipped:         int = 0,
        unfollowed:      int = 0,
        unfollow_failed: int = 0
    ) -> dict:
        summary = {
            "session_followed":        followed,
            "session_skipped":         skipped,
            "session_unfollowed":      unfollowed,
            "session_unfollow_failed": unfollow_failed,
            "followed_today":          self.stats.followed_today,
            "unfollowed_today":        self.stats.unfollowed_today,
            "failed_today":            self.stats.failed_today,
            "total_requests":          self.stats.total_requests,
            "daily_follow_limit":      self.config.daily_follow_limit,
            "daily_unfollow_limit":    self.config.daily_unfollow_limit,
            "remaining_follows":       max(
                0,
                self.config.daily_follow_limit - self.stats.followed_today
            ),
            "remaining_unfollows":     max(
                0,
                self.config.daily_unfollow_limit - self.stats.unfollowed_today
            ),
            "session_start":           self.session_start,
            "session_end":             datetime.now().isoformat()
        }

        logger.info("\n" + "=" * 55)
        logger.info("📊 SESSION SUMMARY")
        logger.info("=" * 55)
        for key, value in summary.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 55)

        return summary
