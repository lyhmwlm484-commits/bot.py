import os
import asyncio
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

# ----------------- הגדרות בסיס -----------------
OWNER_IDS = [
    1401816950060875807,
    1415381659775143991,
    1422851597700038767
]

LOG_CHANNEL_ID = 1558182240297681098  
PLAYER_ROLE_ID = 1555162218591428689  

# קריאת הטוקן דרך משתני סביבה (מתאים ישירות ל-Railway)
TOKEN = os.getenv("DISCORD_TOKEN", "MTU1MTkzNjI2NDkwOTg4NTQ5MA.GHA7Lf.NOCL53O6cwiLj6zeQVD5kecH3_nyQn-8B3SY3I")

# ----------------- מנגנוני הגנה ומעקב -----------------
# מעקב לפעולות אדמין (Anti-Nuke)
action_tracker = defaultdict(lambda: defaultdict(list))

# מעקב להודעות והצטרפויות (Anti-Raid)
user_message_tracker = defaultdict(list)
recent_joins = []
LOCKDOWN_ACTIVE = False
ACCOUNT_MIN_AGE_DAYS = 3  # גיל חשבון מינימלי בימים למניעת רייד של בוטים

def is_whitelisted(user: discord.User | discord.Member, guild: discord.Guild) -> bool:
    return user.id in OWNER_IDS or user.id == guild.owner_id or user.id == bot.user.id

# ----------------- ממשק אימות (Verify) -----------------
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="אמת את עצמך וקבל רול שחקן",
        style=discord.ButtonStyle.green,
        emoji="🎮",
        custom_id="persistent_verify_button"
    )
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        role = guild.get_role(PLAYER_ROLE_ID)

        if not role:
            await interaction.response.send_message("❌ שגיאה: רול שחקן לא נמצא בשרת.", ephemeral=True)
            return

        if role in member.roles:
            await interaction.response.send_message("✨ כבר עברת אימות ויש לך רול שחקן!", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="אימות משתמש - קבלת רול שחקן")
            
            success_embed = discord.Embed(
                title="✅ אומתת בהצלחה!",
                description=f"ברוך הבא לשרת **{guild.name}**!\nקיבלת בהצלחה את הרול **{role.name}** 🎮.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=success_embed, ephemeral=True)

            log_embed = discord.Embed(title="🎮 שחקן חדש אומת בשרת", color=discord.Color.green())
            log_embed.add_field(name="משתמש", value=f"{member.mention} (`{member.id}`)", inline=False)
            log_embed.add_field(name="רול שניתן", value=role.mention, inline=False)
            log_embed.set_footer(text=f"סה״כ חברים בשרת: {guild.member_count}")
            await send_log_embed(guild, log_embed)

        except discord.Forbidden:
            await interaction.response.send_message("⚠️ לבוט אין הרשאה. וודא שרול הבוט ממוקם מעל רול 'שחקן'.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"שגיאה: {e}", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())

bot = MyBot()

async def send_log_embed(guild: discord.Guild, embed: discord.Embed):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"שגיאה בשליחת לוג: {e}")

# ----------------- טיפול בניסיונות ניוק -----------------
async def handle_nuke_attempt(guild: discord.Guild, user: discord.User, action_name: str):
    if is_whitelisted(user, guild):
        return

    member = guild.get_member(user.id)
    if member:
        # הפשטה מיידית של כל רולי הניהול
        try:
            danger_roles = [
                r for r in member.roles 
                if r.permissions.administrator or r.permissions.manage_guild or 
                   r.permissions.manage_channels or r.permissions.manage_roles or 
                   r.permissions.ban_members or r.permissions.kick_members
            ]
            if danger_roles:
                await member.remove_roles(*danger_roles, reason="Anti-Nuke: נטרול הרשאות")
        except Exception:
            pass

    try:
        await guild.ban(user, reason=f"Anti-Nuke Triggered: {action_name}", delete_message_days=1)
        embed = discord.Embed(title="🚨 ניסיון ניוק נבלם!", color=discord.Color.dark_red())
        embed.add_field(name="תוקף", value=f"{user.mention} (`{user.id}`)", inline=False)
        embed.add_field(name="פעולה", value=action_name, inline=False)
        embed.add_field(name="סנקציה", value="הסרת רולים ובאן מיידי", inline=False)
        await send_log_embed(guild, embed)
    except discord.Forbidden:
        print(f"אין לבוט הרשאה לתת באן למשתמש {user.id}")

def check_rate_limit(user_id: int, action_type: str, limit: int, window_seconds: int) -> bool:
    now = datetime.now()
    records = action_tracker[user_id][action_type]
    records = [t for t in records if (now - t).total_seconds() < window_seconds]
    records.append(now)
    action_tracker[user_id][action_type] = records
    return len(records) >= limit

@bot.event
async def on_ready():
    print(f"הבוט מחובר ומאובטח בתור {bot.user}")

# ----------------- פקודת התקנת ווריפי -----------------
@bot.command()
async def setup_verify(ctx):
    if ctx.author.id not in OWNER_IDS and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("אין לך הרשאה לבצע פקודה זו.", delete_after=5)
        return

    try:
        await ctx.message.delete()
    except Exception:
        pass

    embed = discord.Embed(
        title=f"🔒 כניסה ואימות לשרת • {ctx.guild.name}",
        description=(
            "ברוכים הבאים לשרת!\n"
            "כדי לקבל גישה לכל הערוצים ולקבל את הרול **שחקן**, לחצו על הכפתור למטה.\n\n"
            "🎮 **לחצו כאן:**"
        ),
        color=discord.Color.from_rgb(46, 204, 113)
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.set_footer(text="מערכת ההגנה והאימות הרשמית", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed, view=VerifyView())

# ----------------- 1. הגנות הודעות (Anti-Spam & Slash abuse) -----------------
@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        # טיפול בסלאש קומנד של בוטים זרים
        if message.guild and message.author.bot and message.author.id != bot.user.id:
            user_who_used = None
            if hasattr(message, "interaction_metadata") and message.interaction_metadata:
                user_who_used = message.interaction_metadata.user
            elif hasattr(message, "interaction") and message.interaction:
                user_who_used = message.interaction.user

            if user_who_used and not is_whitelisted(user_who_used, message.guild):
                member = message.guild.get_member(user_who_used.id)
                if member and member.top_role < message.guild.me.top_role:
                    try:
                        await member.timeout(timedelta(days=1), reason="שימוש בסלאש של בוט חיצוני")
                        await message.channel.send(f"⚠️ {member.mention} הושתק על שימוש בפקודה לא מורשית.", delete_after=10)
                    except Exception:
                        pass
        return

    # מניעת תיוג אונרים
    if any(uid in OWNER_IDS for uid in [u.id for u in message.mentions]):
        if not is_whitelisted(message.author, message.guild):
            if message.author.top_role < message.guild.me.top_role:
                try:
                    await message.delete()
                    await message.author.timeout(timedelta(minutes=5), reason="תיוג אונר ללא אישור")
                    await message.channel.send(f"⛔ {message.author.mention} הושתק ל-5 דקות עקב תיוג הנהלה.", delete_after=5)
                    return
                except Exception:
                    pass

    # Anti-Mass Mention (מעל 4 תיוגים בהודעה)
    if len(message.mentions) >= 4 and not is_whitelisted(message.author, message.guild):
        try:
            await message.delete()
            await message.author.timeout(timedelta(hours=2), reason="Mass Mention Spam")
            await message.channel.send(f"🚨 {message.author.mention} הושתק על ספאם תיוגים.", delete_after=6)
            return
        except Exception:
            pass

    # Anti-Spam (מעל 5 הודעות ב-4 שניות)
    if not is_whitelisted(message.author, message.guild):
        now = datetime.now()
        history = user_message_tracker[message.author.id]
        history = [t for t in history if (now - t).total_seconds() < 4]
        history.append(now)
        user_message_tracker[message.author.id] = history

        if len(history) >= 5:
            try:
                await message.author.timeout(timedelta(minutes=10), reason="Anti-Spam Triggered")
                await message.channel.send(f"🔇 {message.author.mention} קיבל השתקה ל-10 דקות עקב הצפת צ'אט.", delete_after=6)
            except Exception:
                pass

    await bot.process_commands(message)

# ----------------- 2. מערך Anti-Raid והגנת הצטרפות -----------------
@bot.event
async def on_member_join(member: discord.Member):
    global LOCKDOWN_ACTIVE, recent_joins
    guild = member.guild

    # הגנה נגד בוטים זרים
    if member.bot:
        await asyncio.sleep(1)
        inviter = None
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                if entry.target.id == member.id:
                    inviter = entry.user
                    break
        except Exception:
            pass

        if not inviter or not is_whitelisted(inviter, guild):
            try:
                await member.ban(reason="Anti-Bot: צירוף בוטים חסום")
                if inviter and not is_whitelisted(inviter, guild):
                    await guild.ban(inviter, reason="Anti-Bot: הזמנת בוט לא מאושר")
            except Exception:
                pass
            return

    # זיהוי Raid: מעל 5 משתמשים ב-10 שניות
    now = datetime.now()
    recent_joins = [t for t in recent_joins if (now - t).total_seconds() < 10]
    recent_joins.append(now)

    if len(recent_joins) >= 5 and not LOCKDOWN_ACTIVE:
        LOCKDOWN_ACTIVE = True
        embed = discord.Embed(
            title="🛡️ מצב חירום מופעל (Anti-Raid Lockdown)",
            description="זוהתה כניסה המונית חשודה לשרת! כל משתמש חדש מבודד אוטומטית.",
            color=discord.Color.red()
        )
        await send_log_embed(guild, embed)
        # שחרור נעילה אוטומטי לאחר דקה של רגיעה
        await asyncio.sleep(60)
        LOCKDOWN_ACTIVE = False

    if LOCKDOWN_ACTIVE:
        try:
            await member.kick(reason="Anti-Raid Lockdown Active")
            return
        except Exception:
            pass

    # סינון גיל חשבון (Anti-Alt)
    account_age = (datetime.now(timezone.utc) - member.created_at).days
    if account_age < ACCOUNT_MIN_AGE_DAYS:
        try:
            await member.timeout(timedelta(days=7), reason=f"חשבון חדש מדי ({account_age} ימים)")
            l_embed = discord.Embed(title="⚠️ חשבון חשוד הושתק", color=discord.Color.yellow())
            l_embed.add_field(name="משתמש", value=f"{member.mention} (`{member.id}`)")
            l_embed.add_field(name="גיל החשבון", value=f"{account_age} ימים בלבד")
            await send_log_embed(guild, l_embed)
        except Exception:
            pass

# ----------------- 3. Anti-Nuke: ערוצים (מחיקה ויצירה) -----------------
@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        user = entry.user
        if user and not is_whitelisted(user, guild):
            # מחיקת אפילו ערוץ 1 ללא אישור נחשבת ניוק
            await handle_nuke_attempt(guild, user, f"מחיקת ערוץ ({channel.name})")
        break

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
        user = entry.user
        if user and not is_whitelisted(user, guild):
            if check_rate_limit(user.id, "channel_create", limit=3, window_seconds=10):
                await handle_nuke_attempt(guild, user, "ספאם יצירת ערוצים (Channel Spam)")
        break

# ----------------- 4. Anti-Nuke: רולים (מחיקה ויצירה) -----------------
@bot.event
async def on_guild_role_delete(role: discord.Role):
    guild = role.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        user = entry.user
        if user and not is_whitelisted(user, guild):
            await handle_nuke_attempt(guild, user, f"מחיקת רול ({role.name})")
        break

@bot.event
async def on_guild_role_create(role: discord.Role):
    guild = role.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
        user = entry.user
        if user and not is_whitelisted(user, guild):
            if check_rate_limit(user.id, "role_create", limit=3, window_seconds=10):
                await handle_nuke_attempt(guild, user, "ספאם יצירת רולים (Role Spam)")
        break

# ----------------- 5. Anti-Nuke: באנים וקיקים המוניים -----------------
@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        executor = entry.user
        if executor and not is_whitelisted(executor, guild):
            if check_rate_limit(executor.id, "mass_ban", limit=2, window_seconds=15):
                await handle_nuke_attempt(guild, executor, "ניסיון Mass Ban")
        break

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            executor = entry.user
            if executor and not is_whitelisted(executor, guild):
                if check_rate_limit(executor.id, "mass_kick", limit=2, window_seconds=15):
                    await handle_nuke_attempt(guild, executor, "ניסיון Mass Kick")
            break

# ----------------- 6. Anti-Nuke: יצירת Webhook ועדכון שרת -----------------
@bot.event
async def on_webhooks_update(channel: discord.abc.GuildChannel):
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
        user = entry.user
        if user and not is_whitelisted(user, guild):
            await handle_nuke_attempt(guild, user, f"יצירת Webhook זדוני בערוץ {channel.name}")
        break

bot.run(TOKEN)
