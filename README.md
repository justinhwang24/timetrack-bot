# ⏱️ Discord Time Tracking Bot

A Discord bot to help users log daily activities, view their productivity stats, and compete with others.

## ✨ Features

- 🕒 Log activity by hour, AM/PM, and duration
- 🌍 Set and remember each user's timezone
- 📊 View daily, 7-day, and 30-day average stats
- 🔥 Progress bar graphs for last 7 days
- 🧾 See daily logs
- 🧮 View tallies of activities
- ⚔️ Head-to-head comparisons between users
- 💾 Persistent logging via `userdata.json`

## 🚀 Setup

1. **Clone the repo**:
   ```bash
   git clone https://github.com/yourusername/activity-logger-bot.git
   cd activity-logger-bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create a `.env` file**:
   ```
   DISCORD_TOKEN=your-bot-token-here
   ```

4. **Run the bot**:
   ```bash
   python bot.py
   ```

## 🛠 Commands

| Command             | Description |
|---------------------|-------------|
| `!help`             | List all commands |
| `!settimezone <tz>` | Set your timezone (e.g., `America/New_York`) |
| `!log <hour> <AM|PM> <minutes> <activity>` | Log an activity at a certain time |
| `!remove <hour> <AM|PM>` | Remove logs for a specific hour |
| `!showlog`          | Show today's and yesterday's logs |
| `!tally`            | Show a breakdown of today's activities |
| `!stats [@user]`    | Show detailed stats and graph (optional mention) |
| `!h2h @user1 @user2`| Head-to-head comparison between two users |

## 🕰 Timezones

Timezones follow the IANA naming format (e.g., `America/Los_Angeles`, `Europe/London`, `Asia/Tokyo`). Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

## 🧠 How It Works

- Activity logs are stored as JSON objects in `userdata.json`.
- Each log entry is timestamped in UTC and converted based on user-specific timezones.
- The bot supports both current and legacy logs via user ID and name.
- Visual progress bars (ASCII) display 7-day activity trends.

## 🧪 Example

```text
!log 5 PM 30 math homework
✅ Logged 30 min of 'math homework' at 5 PM on Jul 7.
```

```text
!stats
📊 Stats for @User:
Today: 1h 15m
7-day avg: 1h 2m
30-day avg: 58m

Top activities (last 30 days):
- math homework: 6h 30m
- reading: 2h 45m

Progress (last 7 days):
Mon ████████ 40m
Tue ████████ 55m
...
```

## 📁 File Structure

```
.
├── bot.py             # Main bot logic
├── userdata.json      # Persistent log storage
├── .env               # Token stored here
└── requirements.txt   # Required packages
```

## 📦 Requirements

- Python 3.8+
- `discord.py`
- `pytz`
- `python-dotenv`

Install with:
```bash
pip install discord.py pytz python-dotenv
```
