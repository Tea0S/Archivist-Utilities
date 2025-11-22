# cogs/quests.py
import logging
import os

import discord
from discord.ext import commands
from discord import app_commands
import httpx

from core.config import settings
from core.utils import log_to_council

log = logging.getLogger(__name__)

QUEST_URL = os.getenv("QUEST_GSCRIPT_URL", "").strip()
QUEST_SECRET = os.getenv("QUEST_GSCRIPT_SECRET", "").strip()
GUILD_ID = int(getattr(settings, "GUILD_ID", 0))

# Reservation duration & skip policy
RESERVE_DAYS = 30
MAX_SKIPS = 3


def quest_embed(q: dict, *, info_note: str | None = None, reserved_until: str | None = None) -> discord.Embed:
    title = q.get("title") or "Quest Hook"
    prompt = q.get("prompt") or ""
    e = discord.Embed(title=title, description=prompt)
    e.add_field(name="Type", value=q.get("type") or "-", inline=True)
    e.add_field(name="Max Players", value=str(q.get("max") or "-"), inline=True)
    if reserved_until:
        e.set_footer(text=f"Reserved until {reserved_until}")
    else:
        note = info_note or f"You may skip up to {MAX_SKIPS} times in this session."
        e.set_footer(text=note)
    return e


async def post_quest(payload: dict):
    if not QUEST_URL or not QUEST_SECRET:
        return False, "quest webhook not configured"
    p = {**payload, "secret": QUEST_SECRET}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as x:
            r = await x.post(QUEST_URL, json=p)
        ctype = r.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            return True, r.json()
        return False, f"non-json {r.status_code}"
    except Exception as e:
        return False, str(e)


class AcceptSkipView(discord.ui.View):
    """Buttons attached to the quest card shown in-channel."""
    def __init__(self, user: discord.User, quest: dict):
        super().__init__(timeout=300)
        self.user = user
        self.quest = quest
        self.skips = 0
        # NEW: track the last few titles shown in THIS session (include the current one)
        self.history: list[str] = [quest.get("title") or ""]

    def _recent_excludes(self) -> list[str]:
        # Return up to the last 3 titles (most recent first is fine)
        # If you prefer “last 3 prior to current”, use self.history[-3:] excluding current; but
        # including current ensures we never re-serve it immediately.
        uniq = []
        seen = set()
        for t in reversed(self.history):  # newest → oldest
            lt = (t or "").lower()
            if lt and lt not in seen:
                uniq.append(t)
                seen.add(lt)
            if len(uniq) >= 3:
                break
        return uniq

    async def _reserve(self, interaction: discord.Interaction):
        ok, data = await post_quest({
            "type": "quest_reserve",
            "title": self.quest["title"],
            "user_id": str(self.user.id),
            "user_name": self.user.display_name,
            "days": RESERVE_DAYS
        })
        if ok and isinstance(data, dict) and data.get("ok"):
            until = data["reserved"]["until"]
            await interaction.message.edit(embed=quest_embed(self.quest, reserved_until=until), view=None)
            await interaction.followup.send(
                f"✅ Reserved **{self.quest['title']}** until **{until}**.",
                ephemeral=True
            )
            await log_to_council(interaction.client, f"🗺️ Quest accepted: **{self.user}** → **{self.quest['title']}** (until {until})")
        else:
            await interaction.followup.send(f"❌ Reserve failed: {data}", ephemeral=True)

    async def _reroll(self, interaction: discord.Interaction):
        excludes = self._recent_excludes()  # up to last 3 shown
        ok, data = await post_quest({
            "type": "quest_random",
            "user_id": str(self.user.id),
            "exclude_titles": excludes
        })
        if ok and isinstance(data, dict) and data.get("ok"):
            # If user already has one, show it and stop (remove buttons)
            if data.get("existing"):
                q = data.get("quest") or {}
                await interaction.message.edit(embed=quest_embed(q, reserved_until=q.get("until")), view=None)
                await interaction.followup.send(
                    "ℹ️ You already have an active quest. Use `/quest release` to free it before rolling another.",
                    ephemeral=True
                )
                return
            q = data["quest"]
            self.quest = q
            # Record this new title in session history
            self.history.append(q.get("title") or "")
            remaining = MAX_SKIPS - self.skips
            note = f"Skip remaining: {remaining}. You may skip up to {MAX_SKIPS} times in this session."
            await interaction.message.edit(embed=quest_embed(q, info_note=note), view=self)
            await interaction.followup.send("🔁 Re-rolled a new hook.", ephemeral=True)
        else:
            # Could be 'no alternative quests'
            await interaction.followup.send("❌ No alternative quests right now.", ephemeral=True)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This is not your quest card.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._reserve(interaction)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This is not your quest card.", ephemeral=True)
        if self.skips >= MAX_SKIPS:
            await interaction.response.send_message(
                f"❌ You’ve reached the {MAX_SKIPS}-skip limit for this session. Accept this hook or release your current reservation.",
                ephemeral=True
            )
            btn.disabled = True
            await interaction.message.edit(view=self)
            return
        self.skips += 1
        await interaction.response.defer(ephemeral=True)
        await self._reroll(interaction)

class Quests(commands.Cog):
    """Quest Hooks in-channel: Accept/Skip (max 3 skips per session), 30-day reserve."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    quest_group = app_commands.Group(name="quest", description="Quest management commands")
    
    @quest_group.command(name="start", description="Roll a quest hook here (Accept/Skip up to 3 times).")
    async def quest_start(self, interaction: discord.Interaction):
        # Public response in the channel; show the card here with buttons
        await interaction.response.defer(ephemeral=False, thinking=True)

        ok, data = await post_quest({"type": "quest_random", "user_id": str(interaction.user.id)})
        if not (ok and isinstance(data, dict)):
            return await interaction.followup.send(f"❌ Webhook error: {data}")
        if not data.get("ok"):
            return await interaction.followup.send(f"❌ {data.get('error','unknown error')}")

        # If user already has one, show it (no buttons)
        if data.get("existing"):
            q = data.get("quest") or {}
            e = quest_embed(q, reserved_until=q.get("until"))
            return await interaction.followup.send(embed=e)

        q = data["quest"]
        e = quest_embed(q, info_note=f"You may skip up to {MAX_SKIPS} times in this session.")
        view = AcceptSkipView(interaction.user, q)
        await interaction.followup.send(embed=e, view=view)

    @quest_group.command(name="current", description="Show your current quest reservation (if any).")
    async def quest_current(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, data = await post_quest({"type": "quest_list_user", "user_id": str(interaction.user.id)})
        if ok and isinstance(data, dict) and data.get("ok"):
            qs = data.get("quests") or []
            if not qs:
                return await interaction.followup.send("ℹ️ You don't have an active reservation.", ephemeral=True)
            q = qs[0]
            e = quest_embed(q, reserved_until=q.get("until"))
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Lookup failed: {data}", ephemeral=True)

    @quest_group.command(name="release", description="Release your current reservation.")
    async def quest_release(self, interaction: discord.Interaction, title: str | None = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        # If title omitted, try to fetch user's current
        if not title:
            ok, data = await post_quest({"type": "quest_list_user", "user_id": str(interaction.user.id)})
            if not (ok and isinstance(data, dict) and data.get("ok")):
                return await interaction.followup.send(f"❌ Lookup failed: {data}", ephemeral=True)
            qs = data.get("quests") or []
            if not qs:
                return await interaction.followup.send("ℹ️ You don't have any active reservation.", ephemeral=True)
            title = qs[0].get("title")

        ok, data = await post_quest({"type": "quest_release", "title": title, "user_id": str(interaction.user.id)})
        if ok and isinstance(data, dict) and data.get("ok"):
            await interaction.followup.send("✅ Released your quest.", ephemeral=True)
            await log_to_council(self.bot, f"🗺️ Quest released by **{interaction.user}** ({title}).")
        else:
            await interaction.followup.send(f"❌ Release failed: {data}", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = Quests(bot)
    await bot.add_cog(cog)
    # Add command globally, handle if already registered
    try:
        bot.tree.add_command(cog.quest_group)
    except app_commands.CommandAlreadyRegistered:
        # Command already registered, skip
        pass