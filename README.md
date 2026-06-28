# 🤖 GitHub Auto Following Bot

Automatically **follow** and **unfollow** GitHub users using GitHub Actions.

---

## ✨ Features

- ✅ Auto follow - Target user ගේ followers follow කිරීම
- ✅ Auto unfollow - Bot follow කළ users unfollow කිරීම
- ✅ Daily limits - Account ban වෙන්නේ නෑ
- ✅ Random delays - Bot detection avoid කිරීම
- ✅ Stats tracking - Daily progress track කිරීම
- ✅ Following cache - Bot follow කළ users track කිරීම
- ✅ Rate limit handling - GitHub API limits handle කිරීම
- ✅ GitHub Actions - Free, automated, no server needed

---

## 📁 File Structure

```
GitHub_auto-following_bots/
├── .github/
│   └── workflows/
│       └── follow-bot.yml    # GitHub Actions workflow
├── bot.py                    # Core bot logic
├── main.py                   # Entry point
├── requirements.txt          # Dependencies
├── .gitignore                # Git ignore rules
└── README.md                 # This file
```

---

## 🚀 Setup Guide

### Step 1: Fork or Clone Repository

```bash
git clone https://github.com/yourusername/GitHub_auto-following_bots.git
```

### Step 2: Generate GitHub Token

```
GitHub > Profile > Settings >
Developer settings >
Personal access tokens > Tokens (classic) >
Generate new token (classic)

Note: "follow-bot-token"
Expiration: 90 days

Scopes:
  ✅ user > follow
```

### Step 3: Add Secret

```
Repo > Settings >
Secrets and variables > Actions >
Secrets tab > New repository secret

Name:  FOLLOW_BOT_TOKEN
Value: ghp_xxxxxxxxxxxx
```

### Step 4: Add Variables

```
Repo > Settings >
Secrets and variables > Actions >
Variables tab > New repository variable
```

| Variable | Value | Description |
|----------|-------|-------------|
| `TARGET_USERNAME` | `torvalds` | Follow කළ යුතු user ගේ followers |
| `DAILY_LIMIT` | `300` | දිනකට maximum follows |
| `FOLLOW_LIMIT` | `50` | එක් run එකකට follows |
| `MIN_DELAY` | `30` | අවම delay (seconds) |
| `MAX_DELAY` | `60` | උපරිම delay (seconds) |
| `DAILY_UNFOLLOW_LIMIT` | `300` | දිනකට maximum unfollows |
| `UNFOLLOW_LIMIT` | `50` | එක් run එකකට unfollows |
| `UNFOLLOW_MIN_DELAY` | `30` | Unfollow අවම delay (seconds) |
| `UNFOLLOW_MAX_DELAY` | `60` | Unfollow උපරිම delay (seconds) |

---

## ▶️ Usage

### Auto Schedule (Automatic)

Bot automatically runs:

| Time (IST) | Mode | Description |
|------------|------|-------------|
| 09:00 AM | Follow | Morning follow session |
| 03:00 PM | Follow | Afternoon follow session |
| 09:00 PM | Follow | Evening follow session |
| Sunday 03:00 AM | Unfollow | Weekly unfollow session |

### Manual Run

```
Repo > Actions tab >
GitHub Follow Bot >
Run workflow (button) >

  mode:
    follow   = Follow mode
    unfollow = Unfollow mode

  unfollow_source:
    cache = Bot follow කළ users විතරක් unfollow
    all   = ඔයාගේ සම්පූර්ණ following list unfollow

Run workflow ✅
```

---

## 📊 Bot Modes

### Follow Mode
```
Target user ගේ followers list එකෙන්
නව users follow කිරීම

Example:
  TARGET_USERNAME = torvalds
  FOLLOW_LIMIT    = 50
  → torvalds ගේ followers 50 දෙනෙකුව follow කරනවා
```

### Unfollow Mode - Cache
```
Bot follow කළ users විතරක් unfollow කිරීම
(following_cache.json file එකෙන්)

Safe option - ඔයා manually follow කළ
users effect නොවෙනවා ✅
```

### Unfollow Mode - All
```
ඔයාගේ සම්පූර්ණ following list
unfollow කිරීම

⚠️ Warning: ඔයා manually follow කළ
users ද unfollow වෙනවා!
```

---

## 📈 Stats Tracking

Bot automatically tracks:

```json
{
  "followed_today": 50,
  "unfollowed_today": 0,
  "failed_today": 0,
  "total_requests": 102,
  "last_run_date": "2026-06-27"
}
```

---

## ⚙️ Configuration

### Recommended Settings

```
Conservative (Safe):        Aggressive:
  FOLLOW_LIMIT    = 30        FOLLOW_LIMIT    = 100
  MIN_DELAY       = 45        MIN_DELAY       = 15
  MAX_DELAY       = 90        MAX_DELAY       = 30
  DAILY_LIMIT     = 100       DAILY_LIMIT     = 300
```

### GitHub API Limits

```
Rate limit     : 5000 requests/hour
Follow limit   : ~1000/day (recommended: 300)
Unfollow limit : ~1000/day (recommended: 300)
```

---

## 🔧 Troubleshooting

### Bot not following anyone
```
✅ Check: FOLLOW_BOT_TOKEN secret set කළාද?
✅ Check: TARGET_USERNAME variable set කළාද?
✅ Check: Token scope "user:follow" තියෙනවාද?
✅ Check: Actions tab > workflow enabled කළාද?
```

### Rate limit errors
```
✅ Fix: MIN_DELAY වැඩි කරන්න (30 → 60)
✅ Fix: FOLLOW_LIMIT අඩු කරන්න (50 → 30)
✅ Fix: DAILY_LIMIT අඩු කරන්න (300 → 150)
```

### Token errors
```
✅ Fix: Token expire වෙලාද? නව token හදන්න
✅ Fix: Token scope "user:follow" තියෙනවාද?
✅ Fix: Secret name "FOLLOW_BOT_TOKEN" හරිද?
```

---

## ⚠️ Disclaimer

```
මෙය educational purposes සඳහා පමණි.

GitHub Terms of Service:
  - Automated following discouraged
  - Aggressive following = account suspension

Use responsibly:
  ✅ Low limits use කරන්න
  ✅ High delays use කරන්න
  ✅ Daily limits exceed නොකරන්න
```

---

## 📝 License

MIT License - Free to use and modify.

---

## 🙏 Credits

Built with:
- [GitHub Actions](https://github.com/features/actions)
- [GitHub REST API](https://docs.github.com/en/rest)
- Python `requests` library
