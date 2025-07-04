import discord
import os
import pytz
import json
from discord.ext import commands
from datetime import datetime
from dotenv import load_dotenv
from pytz import all_timezones, timezone
from collections import defaultdict

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

DATA_FILE = "userdata.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

time_logs = []
user_timezones = {}

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
        json.dump({
            "time_logs": time_logs,
            "user_timezones": {str(k): v for k, v in user_timezones.items()}
        }, f, indent=2)

def format_duration(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"
    
@bot.event
async def on_ready():
    load_data()
    print(f"Bot is logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        cmd = ctx.command
        usage = f"{ctx.prefix}{cmd.qualified_name} {cmd.signature}"
        await ctx.send(f"Missing required argument.\n**Usage:** `{usage}`")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're doing that too often. Try again in {error.retry_after:.1f}s.")
    else:
        raise error 

@bot.command(name="commands", aliases=["help"], help="List all available commands.")
async def commands_list(ctx):
    commands_info = []
    for cmd in bot.commands:
        if not cmd.hidden:
            commands_info.append(f"!{cmd.name} - {cmd.help or 'No description provided.'}")

    msg = "**Available Commands:**\n" + "\n".join(commands_info)
    await ctx.send(msg)
    
@bot.command(help="Set your timezone, e.g. America/New_York.")
async def settimezone(ctx, tz: str):
    if tz not in all_timezones:
        await ctx.send(
            "Invalid timezone. Valid examples include:\n"
            "- America/New_York\n- America/Los_Angeles\n- Europe/London\n- Asia/Seoul\n- Asia/Tokyo\n- UTC\n"
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

    if am_pm == "PM" and hour != 12:
        hour += 12
    elif am_pm == "AM" and hour == 12:
        hour = 0

    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)

    now_local = datetime.now(user_tz)
    log_date = now_local.date()

    naive_log_dt = datetime.combine(log_date, datetime.min.time()).replace(hour=hour)

    local_log_dt = user_tz.localize(naive_log_dt)

    utc_log_dt = local_log_dt.astimezone(pytz.UTC)
    utc_iso = utc_log_dt.isoformat()

    user_entries_today = [e for e in time_logs if e["user"] == ctx.author.name and e["date"] == log_date.isoformat()]

    total_minutes_in_hour = 0
    for e in user_entries_today:
        e_utc_dt = datetime.fromisoformat(e["datetime_utc"]).astimezone(user_tz)
        if e_utc_dt.hour == hour:
            total_minutes_in_hour += e["minutes"]

    if total_minutes_in_hour + minutes > 60:
        await ctx.send(f"Error: Total logged minutes in the hour {hour % 12 or 12} {am_pm} would exceed 60 minutes.")
        return

    entry = {
        "user": ctx.author.name,
        "datetime_utc": utc_iso,
        "date": log_date.isoformat(),
        "minutes": minutes,
        "activity": activity.strip().lower()
    }

    time_logs.append(entry)
    save_data()

    tz_abbr = local_log_dt.strftime("%Z")
    await ctx.send(f"Successfully logged {minutes} min of '{activity.strip().lower()}' at {hour % 12 or 12} {am_pm} {tz_abbr} by {ctx.author.name}!")

@bot.command(help="Remove logs for a specific hour today.")
async def remove(ctx, hour: int, am_pm: str):
    am_pm = am_pm.upper().strip()
    if am_pm not in ("AM", "PM"):
        await ctx.send("Please specify AM or PM.")
        return

    if not (1 <= hour <= 12):
        await ctx.send("Hour must be between 1 and 12.")
        return

    if am_pm == "PM" and hour != 12:
        hour += 12
    elif am_pm == "AM" and hour == 12:
        hour = 0

    user = ctx.author.name
    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)
    today = datetime.now(user_tz).strftime("%Y-%m-%d")

    # Filter out logs that match the user, date, and local hour
    global time_logs
    before_count = len(time_logs)

    new_logs = []
    for e in time_logs:
        if e["user"] != user or e["date"] != today:
            new_logs.append(e)
            continue

        try:
            log_dt_local = datetime.fromisoformat(e["datetime_utc"]).astimezone(user_tz)
        except Exception:
            new_logs.append(e)
            continue

        if log_dt_local.hour != hour:
            new_logs.append(e)

    removed_count = before_count - len(new_logs)
    time_logs = new_logs
    save_data()

    if removed_count:
        if removed_count == 1:
            logs_text = "log"
        else:
            logs_text = "logs"
        await ctx.send(f"Removed {removed_count} {logs_text} for {hour % 12 or 12} {am_pm}.")
    else:
        await ctx.send(f"No logs found for {hour % 12 or 12} {am_pm}.")

@bot.command(help="Show your past logged activities.")
async def showlog(ctx):
    user = ctx.author.name
    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)
    now = datetime.now(user_tz)
    tz_abbr = now.strftime("%Z")

    entries = sorted(
        [e for e in time_logs if e["user"] == user],
        key=lambda x: x["datetime_utc"]
    )
    
    if not entries:
        await ctx.send("No logs found.")
        return

    msg = f"Logs for {user} ({tz_abbr}):\n"
    for e in entries:
        try:
            dt_utc = datetime.fromisoformat(e["datetime_utc"])
            dt_local = dt_utc.astimezone(user_tz)
            time_str = dt_local.strftime("%Y-%m-%d at %I:%M %p")
        except Exception:
            time_str = f"{e['date']} at ??"

        msg += f"{time_str} — {e['minutes']} min of {e['activity']}\n"

    await ctx.send(f"```\n{msg.strip()}\n```")

@bot.command(help="Tally your total logged time for today.")
async def tally(ctx):
    user = ctx.author.name
    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)
    date_obj = datetime.now(user_tz)
    today = date_obj.strftime("%Y-%m-%d")
    date_str = f"{date_obj.strftime('%b')} {date_obj.day}"

    entries = [e for e in time_logs if e["user"] == user and e["date"] == today]
    if not entries:
        await ctx.send("No logs found for today.")
        return

    totals = defaultdict(int)
    for e in entries:
        totals[e["activity"]] += e["minutes"]

    total_minutes = sum(totals.values())

    result = f"**{date_str} total for {ctx.author.mention}:** {format_duration(total_minutes)}\n"

    for activity, mins in totals.items():
        result += f"- {activity}: {format_duration(mins)}\n"

    await ctx.send(result.strip())

from collections import defaultdict, Counter
from datetime import datetime, timedelta

@bot.command(help="Show stats: daily totals, averages, top activities, best day, and progress graph.")
async def stats(ctx):
    user = ctx.author.name
    tz_name = user_timezones.get(ctx.author.id, "America/New_York")
    user_tz = timezone(tz_name)

    def str_to_date(dstr):
        return datetime.strptime(dstr, "%Y-%m-%d").date()

    user_logs = [e for e in time_logs if e["user"] == user]
    if not user_logs:
        await ctx.send("No logs found for your user.")
        return

    today_local = datetime.now(user_tz).date()
    date_30_days_ago = today_local - timedelta(days=29)
    date_7_days_ago = today_local - timedelta(days=6)

    daily_totals = defaultdict(int)
    daily_activities = defaultdict(lambda: defaultdict(int))

    for log in user_logs:
        log_date = str_to_date(log["date"])
        daily_totals[log_date] += log["minutes"]
        if log_date >= date_30_days_ago:
            daily_activities[log_date][log["activity"]] += log["minutes"]

    today_total = daily_totals.get(today_local, 0)

    def average_minutes(start_date, end_date):
        day_count = (end_date - start_date).days + 1
        total = sum(daily_totals.get(start_date + timedelta(days=i), 0) for i in range(day_count))
        return total / day_count if day_count > 0 else 0

    avg_7_day = average_minutes(date_7_days_ago, today_local)
    avg_30_day = average_minutes(date_30_days_ago, today_local)

    activity_totals = defaultdict(int)
    for day in daily_activities:
        for act, mins in daily_activities[day].items():
            activity_totals[act] += mins
    activity_totals = dict(sorted(activity_totals.items(), key=lambda x: -x[1]))

    best_day = max(daily_totals.items(), key=lambda x: x[1])
    best_day_str = f"{best_day[0].strftime('%b')} {best_day[0].day}, {best_day[0].year}"
    best_day_minutes = best_day[1]

    max_minutes_7d = max(daily_totals.get(date_7_days_ago + timedelta(days=i), 0) for i in range(7))
    max_minutes_7d = max(max_minutes_7d, 1)
    graph_lines = []
    day_label_width = 4

    for i in range(7):
        d = date_7_days_ago + timedelta(days=i)
        mins = daily_totals.get(d, 0)
        bar_len = int(mins / max_minutes_7d * 10)
        bar = "█" * bar_len
        day_str = d.strftime("%a")
        time_str = format_duration(mins)
        graph_lines.append(f"{day_str.ljust(day_label_width)}{bar:<10} {time_str}")

    msg = (
        f"**:chart_with_upwards_trend: Stats for {ctx.author.mention}:**\n"
        f"Today total: {format_duration(today_total)}\n"
        f"7-day rolling average: {format_duration(int(round(avg_7_day)))} / day\n"
        f"30-day rolling average: {format_duration(int(round(avg_30_day)))} / day\n\n"
        f":pencil: **Activity breakdown (last 30 days):**\n"
    )
    for act, mins in activity_totals.items():
        msg += f"- {act}: {format_duration(mins)}\n"

    msg += f"\n:trophy: **Most logged day ever:** {best_day_str} with {format_duration(best_day_minutes)}\n\n"
    msg += ":signal_strength: **Last 7 days progress:**\n" + "\n".join(graph_lines)

    await ctx.send(msg)

bot.run(TOKEN)