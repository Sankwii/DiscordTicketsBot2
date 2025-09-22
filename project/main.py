# main.py

import os
import asyncio
import json
import traceback

import nextcord
from nextcord import ui, ButtonStyle, Interaction, TextChannel, Embed, PermissionOverwrite, SlashOption
from nextcord.ext import commands
from dotenv import load_dotenv
from datetime import datetime
import aiohttp

from database.models import Base, Ticket, Feedback
from database.session import engine, SessionLocal
from database.crud import create_ticket, close_ticket, get_statistics, create_feedback
from utils.antispam import AntiSpamSystem
from utils.pdf_generator import generate_pdf
from utils.helpers import validate_rating, log_activity

load_dotenv()

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
anti_spam = AntiSpamSystem()

# ─── Setup Database ────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ─── Scanned channels for !send ────────────────────────────────────────────
SCANNED_CHANNELS = set()

# ─── Server 1 config (Anicats) ────────────────────────────────────────────
GUILD_ID_1           = int(os.getenv("GUILD_ID_1", 0))
ADMIN_ROLE_ID_1      = int(os.getenv("ADMIN_ROLE_ID", 0))
SUPPORT_ROLE_ID_1    = int(os.getenv("SUPPORT_ROLE_ID_1", 0))
TICKET_CATEGORY_ID_1 = int(os.getenv("TICKET_CATEGORY_ID", 0))
ADMIN_CHANNEL_ID_1   = int(os.getenv("ADMIN_CHANNEL_ID", 0))

# ─── Server 2 config (Test) ───────────────────────────────────────────────
GUILD_ID_2           = int(os.getenv("GUILD_ID_2", 0))
ADMIN_ROLE_ID_2      = int(os.getenv("ADMIN_ROLE_ID_2", 0))
TICKET_CATEGORY_ID_2 = int(os.getenv("TICKET_CATEGORY_ID_2", 0))
ADMIN_CHANNEL_ID_2   = int(os.getenv("ADMIN_CHANNEL_ID_2", 0))

# ─── Verification roles ───────────────────────────────────────────────────
VERIFIED_ROLE_ID   = int(os.getenv("VERIFIED_ROLE_ID", 0))
REQUIRED_ROLE_ID   = int(os.getenv("REQUIRED_ROLE_ID", 0))
UNVERIFIED_ROLE_ID = int(os.getenv("UNVERIFIED_ROLE_ID", 0))


def get_config_for_guild(guild_id: int):
    if guild_id == GUILD_ID_1:
        return ADMIN_ROLE_ID_1, SUPPORT_ROLE_ID_1, TICKET_CATEGORY_ID_1, ADMIN_CHANNEL_ID_1
    elif guild_id == GUILD_ID_2:
        return ADMIN_ROLE_ID_2, None, TICKET_CATEGORY_ID_2, ADMIN_CHANNEL_ID_2
    else:
        return None, None, None, None


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
        return
    print(f"[ERROR] Command {ctx.command} raised {error}")
    traceback.print_exc()


# ─── Verification command ─────────────────────────────────────────────────
@bot.command(name="верификация")
@commands.has_role(REQUIRED_ROLE_ID)
async def верификация(ctx: commands.Context, member: nextcord.Member):
    verified_role   = ctx.guild.get_role(VERIFIED_ROLE_ID)
    unverified_role = ctx.guild.get_role(UNVERIFIED_ROLE_ID)

    if not verified_role:
        return await ctx.send("❌ Роль верификации не найдена!", delete_after=10)
    if verified_role in member.roles:
        return await ctx.send(f"⚠️ {member.mention} уже верифицирован!", delete_after=5)

    try:
        await member.add_roles(verified_role)
        if unverified_role and unverified_role in member.roles:
            await member.remove_roles(unverified_role)
        await ctx.send(f"✅ {member.mention} успешно верифицирован!", delete_after=5)
    except nextcord.Forbidden:
        await ctx.send("❌ Недостаточно прав для выдачи роли.", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Ошибка: {e}", delete_after=10)

@верификация.error
async def верификация_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ У вас нет прав для этой команды.", delete_after=5)


# ─── Ticket creation UI ───────────────────────────────────────────────────
class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TagSelect())

class TagSelect(ui.Select):
    def __init__(self):
        options = [
            nextcord.SelectOption(label="Срочно", emoji="🔥", value="urgent"),
            nextcord.SelectOption(label="Вопрос", emoji="❓", value="question"),
            nextcord.SelectOption(label="Баг", emoji="🐛", value="bug"),
        ]
        super().__init__(placeholder="Выберите тип тикета…", options=options)

    async def callback(self, interaction: Interaction):
        admin_id, support_id, category_id, _ = get_config_for_guild(interaction.guild.id)
        is_admin   = admin_id   and any(r.id == admin_id   for r in interaction.user.roles)
        is_support = support_id and any(r.id == support_id for r in interaction.user.roles)

        if not (is_admin or is_support) and anti_spam.check_spam(interaction.user.id):
            anti_spam.log_activity(interaction.user.id)
            return await interaction.response.send_message(
                "❌ Слишком много запросов! Попробуйте позже.", ephemeral=True
            )
        await interaction.response.send_modal(TicketModal(self.values[0]))

class TicketModal(ui.Modal):
    def __init__(self, tag: str):
        super().__init__(title="Создание тикета")
        self.tag = tag
        self.issue = ui.TextInput(
            label="Опишите проблему",
            style=nextcord.TextInputStyle.paragraph,
            required=True, max_length=1000
        )
        self.add_item(self.issue)

    async def callback(self, interaction: Interaction):
        admin_id, support_id, category_id, _ = get_config_for_guild(interaction.guild.id)
        try:
            with SessionLocal() as db:
                if db.query(Ticket).filter(Ticket.content == self.issue.value).first():
                    return await interaction.response.send_message(
                        "❌ Такой тикет уже существует!", ephemeral=True
                    )
                ticket = create_ticket(db, interaction.user.id, self.issue.value, self.tag)
            log_activity(f"ticket created user={interaction.user.id} id={ticket.id}")
            await self._create_channel(interaction, ticket, admin_id, support_id, category_id)
        except Exception:
            traceback.print_exc()
            await interaction.response.send_message("❌ Ошибка при создании тикета.", ephemeral=True)

    async def _create_channel(self, interaction, ticket, admin_id, support_id, category_id):
        if not category_id:
            return await interaction.response.send_message("❌ Категория не настроена.", ephemeral=True)
        category = interaction.guild.get_channel(category_id)
        if not category:
            return await interaction.response.send_message("❌ Категория не найдена.", ephemeral=True)

        overwrites = {
            interaction.guild.default_role: PermissionOverwrite(view_channel=False),
            interaction.user:                PermissionOverwrite(view_channel=True, send_messages=True),
            bot.user:                        PermissionOverwrite(view_channel=True, manage_channels=True)
        }
        if admin_id:
            overwrites[interaction.guild.get_role(admin_id)] = PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True
            )
        if support_id:
            overwrites[interaction.guild.get_role(support_id)] = PermissionOverwrite(
                view_channel=True, send_messages=True
            )

        channel = await category.create_text_channel(f"ticket-{ticket.id}", overwrites=overwrites)
        tpl = json.load(open("templates/response_template.json", encoding="utf-8"))

        embed = Embed(
            title=f"Тикет #{ticket.id} {tpl['tags'][self.tag]}",
            description=f"**{interaction.user.mention}**\n{self.issue.value}",
            color=nextcord.Color.green()
        )
        view = ui.View()
        view.add_item(ui.Button(style=ButtonStyle.red, label="Закрыть тикет", custom_id="close_ticket"))

        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Тикет создан: {channel.mention}", ephemeral=True)


# ─── Feedback UI ─────────────────────────────────────────────────────────
class FeedbackView(ui.View):
    def __init__(self, ticket_id, creator_id, guild_id):
        super().__init__(timeout=None)
        self.ticket_id  = ticket_id
        self.creator_id = int(creator_id)   # ← приводим к int
        self.guild_id   = guild_id
        for i in range(1, 6):
            btn = ui.Button(label=str(i), style=ButtonStyle.blurple, custom_id=f"rate_{i}")
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, rating):
        async def cb(interaction: Interaction):
            if interaction.user.id != self.creator_id:
                print(f"[DEBUG] Отзыв отклонён: user={interaction.user.id}, creator={self.creator_id}")
                return await interaction.response.send_message(
                    "❌ Только создатель может оставить отзыв.", ephemeral=True
                )
            await interaction.response.send_modal(
                FeedbackModal(self.ticket_id, self.creator_id, rating, self.guild_id)
            )
        return cb

class FeedbackModal(ui.Modal):
    def __init__(self, ticket_id, creator_id, rating, guild_id):
        super().__init__(title="Обратная связь")
        self.ticket_id  = ticket_id
        self.creator_id = creator_id
        self.rating     = rating
        self.guild_id   = guild_id
        self.comment    = ui.TextInput(
            label="Комментарий",
            style=nextcord.TextInputStyle.paragraph,
            required=False, max_length=500
        )
        self.add_item(self.comment)

    async def callback(self, interaction: Interaction):
        try:
            with SessionLocal() as db:
                fb = create_feedback(db, interaction.user.id, self.rating, comment=self.comment.value or None, ticket_id=self.ticket_id)
            if not fb:
                return await interaction.response.send_message("❌ Отзыв уже оставлен.", ephemeral=True)
            log_activity(f"feedback user={interaction.user.id} rating={self.rating} ticket={self.ticket_id}")

            creator = await bot.fetch_user(self.creator_id)
            await creator.send(embed=Embed(
                title="Твой тикет оценён",
                description=f"#{self.ticket_id}: {self.rating}/5\n{self.comment.value or ''}",
                color=nextcord.Color.gold()
            ))

            _, _, _, admin_ch = get_config_for_guild(self.guild_id)
            ch = bot.get_channel(admin_ch)
            if ch:
                await ch.send(embed=Embed(
                    title=f"Новый отзыв: {self.rating}/5",
                    description=self.comment.value or "Без комментария",
                    color=nextcord.Color.gold()
                ).add_field(name="Ticket", value=str(self.ticket_id)))

            await interaction.response.send_message("✅ Спасибо за отзыв!", ephemeral=True)
        except Exception:
            traceback.print_exc()
            await interaction.response.send_message("❌ Ошибка при сохранении отзыва.", ephemeral=True)


# ─── Core commands/events ─────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Бот запущен: {bot.user}")
    bot.add_view(TicketView())

@bot.command()
@commands.has_permissions(administrator=True)
async def scan(ctx):
    SCANNED_CHANNELS.clear()
    for ch in ctx.guild.text_channels:
        SCANNED_CHANNELS.add(ch.id)
    await ctx.send(f"✅ Отсканировано {len(SCANNED_CHANNELS)} каналов.", delete_after=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def send(ctx, channel: TextChannel):
    admin_id, support_id, _, _ = get_config_for_guild(ctx.guild.id)
    is_admin   = admin_id and any(r.id == admin_id for r in ctx.author.roles)
    is_support = support_id and any(r.id == support_id for r in ctx.author.roles)
    if not (is_admin or is_support):
        return await ctx.send("❌ Нет прав для !send.", delete_after=5)
    if channel.id not in SCANNED_CHANNELS:
        return await ctx.send("❌ Канал не отсканирован. Сначала !scan.", delete_after=5)
    embed = Embed(
        title="🎫 Техническая поддержка",
        description="Нажмите кнопку, чтобы создать тикет",
        color=nextcord.Color.blue()
    )
    await channel.send(embed=embed, view=TicketView())
    await ctx.send(f"✅ Панель отправлена в {channel.mention}", delete_after=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    embed = Embed(
        title="🎫 Техническая поддержка",
        description="Нажмите кнопку, чтобы создать тикет",
        color=nextcord.Color.blue()
    )
    await ctx.send(embed=embed, view=TicketView())
    await ctx.send("✅ Система настроена!", delete_after=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def stats(ctx):
    with SessionLocal() as db:
        stats = get_statistics(db)
    embed = Embed(title="📊 Статистика тикетов", color=0x00ff00)
    embed.add_field(name="Всего", value=stats["total_tickets"])
    embed.add_field(name="Открытые", value=stats["open_tickets"])
    embed.add_field(name="Средняя оценка", value=f"{stats['avg_rating']:.2f}/5")
    await ctx.send(embed=embed)

@bot.event
async def on_interaction(interaction: Interaction):
    if interaction.type != nextcord.InteractionType.component:
        return
    if interaction.data.get("custom_id") == "close_ticket":
        admin_id, support_id, _, _ = get_config_for_guild(interaction.guild.id)
        is_admin   = admin_id and any(r.id == admin_id for r in interaction.user.roles)
        is_support = support_id and any(r.id == support_id for r in interaction.user.roles)
        if not (is_admin or is_support):
            return await interaction.response.send_message("❌ Нет прав закрывать тикеты.", ephemeral=True)
        await handle_ticket_close(interaction)

async def handle_ticket_close(interaction: Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except:
        pass

    channel = interaction.channel
    ticket_id = int(channel.name.split("-", 1)[1])

    with SessionLocal() as db:
        ticket = close_ticket(db, ticket_id)
        creator_id = ticket.user_id
        issue_txt  = ticket.content

    history = await channel.history(limit=100).flatten()
    logs, atts = [], []
    for msg in reversed(history):
        logs.append({"author": str(msg.author), "content": msg.content or ""})
        atts.extend(msg.attachments)

    local_atts = []
    async with aiohttp.ClientSession() as sess:
        for att in atts:
            save_dir = os.path.join(os.getcwd(), "attachments")
            os.makedirs(save_dir, exist_ok=True)
            fname = f"{att.id}_{att.filename}"
            path  = os.path.join(save_dir, fname)
            try:
                async with sess.get(att.url) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        local_atts.append((path, att.url))
            except:
                pass

    creator = interaction.guild.get_member(creator_id) or await bot.fetch_user(creator_id)
    creator_name = getattr(creator, "display_name", getattr(creator, "name", str(creator_id)))

    pdf_path = generate_pdf(str(ticket_id), creator_name, issue_txt, logs, local_atts)
    log_activity(f"PDF generated: ticket={ticket_id} file={pdf_path}")

    try:
        await creator.send(
            embed=Embed(
                title="Ваш тикет закрыт",
                description="Пожалуйста, оцените работу от 1 до 5",
                color=nextcord.Color.gold()
            ),
            view=FeedbackView(ticket_id, creator_id, interaction.guild.id)
        )
    except:
        _, _, _, admin_ch = get_config_for_guild(interaction.guild.id)
        await bot.get_channel(admin_ch).send(f"Не удалось DM {creator_id} по закрытию #{ticket_id}")

    await interaction.followup.send("✅ Канал удалится через 10 секунд.", ephemeral=True)
    await asyncio.sleep(10)
    try:
        await channel.delete()
    except:
        pass

@bot.slash_command(name="ticket_slash", description="Создать тикет через Slash", guild_ids=[GUILD_ID_1, GUILD_ID_2])
async def ticket_slash(interaction: Interaction, тема: str = SlashOption(description="Описание проблемы", required=True)):
    admin_id, support_id, cat_id, _ = get_config_for_guild(interaction.guild.id)
    is_admin   = admin_id and any(r.id == admin_id for r in interaction.user.roles)
    is_support = support_id and any(r.id == support_id for r in interaction.user.roles)
    if not (is_admin or is_support) and anti_spam.check_spam(interaction.user.id):
        anti_spam.log_activity(interaction.user.id)
        return await interaction.response.send_message("❌ Слишком много запросов!", ephemeral=True)
    if not cat_id:
        return await interaction.response.send_message("⚠️ Конфигурация не найдена.", ephemeral=True)

    overwrites = {
        interaction.guild.default_role: PermissionOverwrite(view_channel=False),
        interaction.user:                PermissionOverwrite(view_channel=True, send_messages=True),
        bot.user:                        PermissionOverwrite(view_channel=True, manage_channels=True)
    }
    if admin_id:
        overwrites[interaction.guild.get_role(admin_id)] = PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
    if support_id:
        overwrites[interaction.guild.get_role(support_id)] = PermissionOverwrite(view_channel=True, send_messages=True)

    channel = await interaction.guild.get_channel(cat_id).create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites)
    with SessionLocal() as db:
        ticket = create_ticket(db, interaction.user.id, тема, "slash")

    embed = Embed(
        title=f"Тикет #{ticket.id}",
        description=f"**{interaction.user.mention}**\n\n{тема}",
        color=nextcord.Color.green()
    )
    view = ui.View()
    view.add_item(ui.Button(style=ButtonStyle.red, label="Закрыть тикет", custom_id="close_ticket"))

    await channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Создан: {channel.mention}", ephemeral=True)


if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))
