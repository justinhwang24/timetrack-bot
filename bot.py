import discord
import os
import pytz
import json
from discord.ext import commands
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pytz import all_timezones, timezone
from collections import defaultdict, Counter

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

DATA_FILE = "userdata.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

time_logs = []
user_timezones = {}

# ────────────────────────────
# Persistence helpers
# ────────────────────────────
def load_data():
    global time_logs, user_timezones
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            time_logs = data.get("time_logs", [])
            user_timezones = {int(k): v for k, v in data.get("user_timezones", {}).items()}
    else:
        time_logs = []
        user_timezones = {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(
            {
                "time_logs": time_logs,
                "user_timezones": {str(k): v for k, v in user_timezones.items()},
            },
            f,
            indent=2,
        )

# ────────────────────────────
# Utility helpers
# ────────────────────────────
def format_duration(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"

def str_to_date(dstr: str) -> datetime.date:
    return datetime.strptime(dstr, "%Y-%m-%d").date()

def compute_user_stats(user_id: int, user_name: str, tz_name: str):
    """Return today_total, 7-day avg, 30-day avg, last-7-list, activity_totals."""
    user_tz = timezone(tz_name)

    # Pull all logs for this user (support both id-based and legacy name-based records)
    logs = [
        e
        for e in time_logs
        if e.get("user_id") == user_id or e["user"] == user_name
    ]
    if not logs:
        return 0, 0, 0, [0] * 7, {}

    today_local = datetime.now(user_tz).date()
    date_30_days_ago = today_local - timedelta(days=29)
    date_7_days_ago = today_local - timedelta(days=6)

    daily_totals = defaultdict(int)
    activity_totals_30d = defaultdict(int)

    for log in logs:
        log_date = str_to_date(log["date"])
        # Daily totals (all-time)
        daily_totals[log_date] += log["minutes"]
        # Activity totals (rolling 30 days)
        if log_date >= date_30_days_ago:
            activity_totals_30d[log["activity"]] += log["minutes"]

    # Core metrics
    today_total = daily_totals.get(today_local, 0)

    def avg_between(start_date, end_date):
        span = (end_date - start_date).days + 1
        total = sum(
            daily_totals.get(start_date + timedelta(days=i), 0) for i in range(span)
        )
        return total / span if span else 0

    avg_7 = avg_between(date_7_days_ago, today_local)
    avg_30 = avg_between(date_30_days_ago, today_local)

    # Last-7-days list (oldest→newest)
    last7 = [
        daily_totals.get(date_7_days_ago + timedelta(days=i), 0) for i in range(7)
    ]

    # Limit to top-5 activities
    top_activities = dict(
        Counter(activity_totals_30d).most_common(5)
    )

    return today_total, avg_7, avg_30, last7, top_activities

# ────────────────────────────
# Events & error handling
# ────────────────────────────
@bot.event
async def on_ready():
    load_data()
    print(f"Bot is logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        usage = f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"
        await ctx.send(f"Missing required argument.\n**Usage:** {usage}")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're doing that too often. Try again in {error.retry_after:.1f}s.")
    else:
        raise error

# ────────────────────────────
# Core commands
# ────────────────────────────
@bot.command(name="commands", aliases=["help"], help="List all available commands.")
async def commands_list(ctx):
    commands_info = [
        f"!{cmd.name} - {cmd.help or 'No description provided.'}"
        for cmd in bot.commands
        if not cmd.hidden
    ]
    await ctx.send("**Available Commands:**\n" + "\n".join(commands_info))

@bot.command(help="Set your timezone, e.g. America/New_York.")
async def settimezone(ctx, tz: str):
    if tz not in all_timezones:
        await ctx.send(
            "Invalid timezone. Examples:\n"
            "- America/New_York\n- America/Los_Angeles\n- Europe/London\n- Asia/Seoul\n- UTC\n"
            "Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        )
        return
    user_timezones[ctx.author.id] = tz
    save_data()
    await ctx.send(f"Timezone set to {tz} for {ctx.author.name}")

@bot.command(help="Log an activity with time and duration.")
async def log(ctx, hour: int, am_pm: str, minutes: int, *, activity: str):
    am_pm = am_pm.upper()
    if am_pm not in ("AM", "PM"):
        await ctx.send("Please use AM or PM.")
        return
    if not (1 <= hour <= 12):
        await ctx.send("Hour must be between 1 and 12.")
        return
    if minutes < 0:
        await ctx.send("Minutes must be a nonnegative number.")
        return

    # Convert to 24-hour local time
    if am_pm == "PM" and hour != 12:
        hour += 12
    elif am_pm == "AM" and hour == 12:
        hour = 0

    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)
    now_local = datetime.now(user_tz)
    log_date = now_local.date()

    # Build a localized datetime
    naive_dt = datetime.combine(log_date, datetime.min.time()).replace(hour=hour)
    local_dt = user_tz.localize(naive_dt)
    utc_iso = local_dt.astimezone(pytz.UTC).isoformat()

    # Ensure we don’t exceed 60 min in that hour
    existing_minutes = sum(
        e["minutes"]
        for e in time_logs
        if (e.get("user_id") == ctx.author.id or e["user"] == ctx.author.name)
        and e["date"] == log_date.isoformat()
        and datetime.fromisoformat(e["datetime_utc"]).astimezone(user_tz).hour == hour
    )
    if existing_minutes + minutes > 60:
        await ctx.send(
            f"Error: Total logged minutes in the hour {hour % 12 or 12} {am_pm} would exceed 60."
        )
        return

    time_logs.append(
        {
            "user": ctx.author.name,       # legacy
            "user_id": ctx.author.id,      # stable ID
            "datetime_utc": utc_iso,
            "date": log_date.isoformat(),
            "minutes": minutes,
            "activity": activity.strip().lower(),
        }
    )
    save_data()

    tz_abbr = local_dt.strftime("%Z")
    await ctx.send(
        f"Logged {minutes} min of '{activity.strip().lower()}' at "
        f"{hour % 12 or 12} {am_pm} {tz_abbr} for {ctx.author.mention}!"
    )

@bot.command(help="Remove logs for a specific hour today.")
async def remove(ctx, hour: int, am_pm: str):
    am_pm = am_pm.upper()
    if am_pm not in ("AM", "PM") or not (1 <= hour <= 12):
        await ctx.send("Usage: !remove <hour> <AM|PM>")
        return

    if am_pm == "PM" and hour != 12:
        hour += 12
    elif am_pm == "AM" and hour == 12:
        hour = 0

    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)
    today = datetime.now(user_tz).strftime("%Y-%m-%d")

    global time_logs
    before = len(time_logs)
    time_logs = [
        e
        for e in time_logs
        if not (
            (e.get("user_id") == ctx.author.id or e["user"] == ctx.author.name)
            and e["date"] == today
            and datetime.fromisoformat(e["datetime_utc"]).astimezone(user_tz).hour == hour
        )
    ]
    removed = before - len(time_logs)
    save_data()
    await ctx.send(
        f"Removed {removed} log{'s' if removed != 1 else ''} for "
        f"{hour % 12 or 12} {am_pm}." if removed else "No logs found to remove."
    )

@bot.command(help="Show your past logged activities.")
async def showlog(ctx):
    target = ctx.author
    user_name = target.name
    tz_name = user_timezones.get(target.id, "America/New_York")
    user_tz = timezone(tz_name)

    entries = sorted(
        [
            e
            for e in time_logs
            if e.get("user_id") == target.id or e["user"] == user_name
        ],
        key=lambda x: x["datetime_utc"],
    )
    if not entries:
        await ctx.send("No logs found.")
        return

    out_lines = []
    for e in entries:
        dt_local = datetime.fromisoformat(e["datetime_utc"]).astimezone(user_tz)
        ts = dt_local.strftime("%Y-%m-%d at %I:%M %p")
        out_lines.append(f"{ts} — {e['minutes']} min of {e['activity']}")

    await ctx.send(f"**Logs for {target.mention}:**\n" + "\n".join(out_lines))

@bot.command(help="Tally your total logged time for today.")
async def tally(ctx):
    user_id = ctx.author.id
    user_name = ctx.author.name
    tz_name = user_timezones.get(user_id, "America/New_York")
    user_tz = timezone(tz_name)
    today = datetime.now(user_tz).strftime("%Y-%m-%d")

    entries = [
        e
        for e in time_logs
        if (e.get("user_id") == user_id or e["user"] == user_name) and e["date"] == today
    ]
    if not entries:
        await ctx.send("No logs found for today.")
        return

    totals = defaultdict(int)
    for e in entries:
        totals[e["activity"]] += e["minutes"]

    total_minutes = sum(totals.values())
    msg = f"**Today’s total for {ctx.author.mention}:** {format_duration(total_minutes)}\n"
    msg += "\n".join(f"- {act}: {format_duration(mins)}" for act, mins in totals.items())
    await ctx.send(msg)

# ────────────────────────────
# Enhanced !stats (supports other users + top-5 activities)
# ────────────────────────────
@bot.command(help="Show stats (optionally for another user). Usage: !stats [@user]")
async def stats(ctx, target: discord.Member = None):
    target = target or ctx.author
    tz_name = user_timezones.get(target.id, "America/New_York")

    today, avg7, avg30, last7, top_acts = compute_user_stats(
        target.id, target.name, tz_name
    )
    if today == avg7 == avg30 == 0 and sum(last7) == 0:
        await ctx.send(f"No logs found for {target.mention}.")
        return

    # Build progress graph
    max_7 = max(max(last7), 1)
    start_day = datetime.now(timezone(tz_name)).date() - timedelta(days=6)
    graph_lines = []
    for i in range(7):
        d = start_day + timedelta(days=i)
        bar = "█" * int(last7[i] / max_7 * 10)
        graph_lines.append(
            f"{d.strftime('%a').ljust(4)}{bar:<10} {format_duration(last7[i])}"
        )

    msg = (
        f"**📊 Stats for {target.mention}:**\n"
        f"Today: {format_duration(today)}\n"
        f"7-day avg: {format_duration(int(round(avg7)))} / day\n"
        f"30-day avg: {format_duration(int(round(avg30)))} / day\n\n"
        f"**Top activities (last 30 days):**\n"
    )
    for act, mins in top_acts.items():
        msg += f"- {act}: {format_duration(mins)}\n"

    msg += "\n**Progress (last 7 days):**\n" + "\n".join(graph_lines)
    await ctx.send(msg)

# ────────────────────────────
# New !h2h command
# ────────────────────────────
@bot.command(help="Head-to-head comparison. Usage: !h2h @user1 @user2")
async def h2h(ctx, user1: discord.Member, user2: discord.Member):
    tz1 = user_timezones.get(user1.id, "America/New_York")
    tz2 = user_timezones.get(user2.id, "America/New_York")

    t1_today, t1_avg7, t1_avg30, last7_1, _ = compute_user_stats(
        user1.id, user1.name, tz1
    )
    t2_today, t2_avg7, t2_avg30, last7_2, _ = compute_user_stats(
        user2.id, user2.name, tz2
    )

    if sum(last7_1) == sum(last7_2) == 0:
        await ctx.send("No logs found for either user.")
        return

    # Combined max for scaling
    combined_max = max(max(last7_1), max(last7_2), 1)
    start_day = datetime.now(timezone(tz1)).date() - timedelta(days=6)
    graph_lines = []
    for i in range(7):
        d = start_day + timedelta(days=i)
        bar1 = "█" * int(last7_1[i] / combined_max * 10)
        bar2 = "█" * int(last7_2[i] / combined_max * 10)
        graph_lines.append(
            f"{d.strftime('%a').ljust(3)} "
            f"{user1.name[:3].ljust(3)} {bar1:<10} {format_duration(last7_1[i]).rjust(6)} | "
            f"{user2.name[:3].ljust(3)} {bar2:<10} {format_duration(last7_2[i]).rjust(6)}"
        )

    msg = (
        f"**⚔️ Head-to-Head: {user1.mention} vs {user2.mention}**\n\n"
        f"**Today:** {user1.name} {format_duration(t1_today)} | "
        f"{user2.name} {format_duration(t2_today)}\n"
        f"**7-day avg:** {user1.name} {format_duration(int(round(t1_avg7)))}/day | "
        f"{user2.name} {format_duration(int(round(t2_avg7)))}/day\n"
        f"**30-day avg:** {user1.name} {format_duration(int(round(t1_avg30)))}/day | "
        f"{user2.name} {format_duration(int(round(t2_avg30)))}/day\n\n"
        f"**Progress (last 7 days):**\n" + "\n".join(graph_lines)
    )
    await ctx.send(msg)

# ────────────────────────────
bot.run(TOKEN)
