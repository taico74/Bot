import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime
import os

# ================= CONFIG =================

from dotenv import load_dotenv

load_dotenv()  # charge le fichier .env automatiquement

TOKEN = os.getenv("DISCORD_TOKEN")


GUILD_ID = 1408086326011494480
VOICE_CHANNEL_ID = 1463228648357101639   # salon vocal tracké
TEXT_CHANNEL_ID = 1463232845316358297    # salon texte où le bot répond

DB = "data.db"
# ==========================================

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
            user_id INTEGER PRIMARY KEY,
            join_time TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_time (
            date TEXT PRIMARY KEY,
            seconds INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            done INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO settings VALUES ('time_goal', 10800)"
        )
        await db.commit()

# ================= EVENTS =================
@bot.event
async def on_ready():
    await init_db()
    print(f"Bot connecté : {bot.user}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    async with aiosqlite.connect(DB) as db:

        # JOIN salon suivi
        if after.channel and after.channel.id == VOICE_CHANNEL_ID:
            await db.execute(
                "INSERT OR REPLACE INTO voice_sessions VALUES (?, ?)",
                (member.id, datetime.now().isoformat())
            )

        # LEAVE salon suivi
        if before.channel and before.channel.id == VOICE_CHANNEL_ID:
            cur = await db.execute(
                "SELECT join_time FROM voice_sessions WHERE user_id = ?",
                (member.id,)
            )
            row = await cur.fetchone()

            if row:
                join_time = datetime.fromisoformat(row[0])
                duration = int((datetime.now() - join_time).total_seconds())
                today = datetime.now().strftime("%Y-%m-%d")

                await db.execute("""
                INSERT INTO daily_time (date, seconds)
                VALUES (?, ?)
                ON CONFLICT(date)
                DO UPDATE SET seconds = seconds + ?
                """, (today, duration, duration))

                await db.execute(
                    "DELETE FROM voice_sessions WHERE user_id = ?",
                    (member.id,)
                )

        await db.commit()

# ================= UTILS =================
async def send_to_stats_channel(message: str):
    channel = bot.get_channel(TEXT_CHANNEL_ID)
    if channel:
        await channel.send(message)

# ================= COMMANDS =================

@bot.command()
async def time(ctx):
    today = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT seconds FROM daily_time WHERE date = ?",
            (today,)
        )
        row = await cur.fetchone()

    total = row[0] if row else 0
    h, m = divmod(total // 60, 60)

    await send_to_stats_channel(
        f"⏱️ Temps vocal aujourd’hui : **{h}h {m}min**"
    )

@bot.command()
async def settimegoal(ctx, hours: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE settings SET value = ? WHERE key = 'time_goal'",
            (hours * 3600,)
        )
        await db.commit()

    await send_to_stats_channel(
        f"🎯 Objectif journalier défini à **{hours}h**"
    )

@bot.command()
async def addgoal(ctx, *, text: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO goals (text, done) VALUES (?, 0)",
            (text,)
        )
        await db.commit()

    await send_to_stats_channel(f"➕ Objectif ajouté : **{text}**")

@bot.command()
async def goals(ctx):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, text, done FROM goals"
        )
        rows = await cur.fetchall()

    if not rows:
        await send_to_stats_channel("📭 Aucun objectif")
        return

    msg = "📝 **Objectifs du jour**\n"
    for gid, text, done in rows:
        msg += f"{gid}. {'✅' if done else '❌'} {text}\n"

    await send_to_stats_channel(msg)

@bot.command()
async def done(ctx, goal_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE goals SET done = 1 WHERE id = ?",
            (goal_id,)
        )
        await db.commit()

    await send_to_stats_channel("✅ Objectif validé")

@bot.command()
async def removegoal(ctx, goal_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "DELETE FROM goals WHERE id = ?",
            (goal_id,)
        )
        await db.commit()

    await send_to_stats_channel("🗑️ Objectif supprimé")

# ================= START =================
bot.run(TOKEN)
