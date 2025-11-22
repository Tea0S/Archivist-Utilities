import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from rapidfuzz import fuzz, process
from cogs.index_manager import IndexConfig
from core.utils import is_owner_or_admin

class Characters(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.thread_cache = {}  # dict of guild_id -> list of (thread_id, title, origin)
        self.config = IndexConfig()
        self.refresh_cache_task.start()  # start background loop

    async def build_cache(self, guild: discord.Guild):
        """Build or rebuild the cache of thread titles for a guild."""
        guild_id = guild.id
        self.thread_cache[guild_id] = []
        
        # Get all configured character forums for this guild
        forum_ids = self.config.get_character_forums(guild_id)
        if not forum_ids:
            print(f"[character-cog] No character forums configured for guild {guild_id}")
            return
        
        total_threads = 0
        for forum_id in forum_ids:
            forum = guild.get_channel(forum_id)
            if not forum or not isinstance(forum, discord.ForumChannel):
                print(f"[character-cog] Character forum {forum_id} not found or not a forum")
                continue

            # Collect threads (active + archived), excluding anything named "index"
            threads = list(forum.threads)
            async for t in forum.archived_threads(limit=None):
                threads.append(t)

            for thread in threads:
                # Exclude threads with "index" in the name (case-insensitive)
                if "index" in thread.name.lower():
                    continue
                
                self.thread_cache[guild_id].append((thread.id, thread.name, forum.name))
                total_threads += 1

        print(f"[character-cog] Cached {total_threads} threads from {len(forum_ids)} forum(s) for guild {guild_id}.")

    @tasks.loop(hours=24)
    async def refresh_cache_task(self):
        """Background task to refresh cache every 24 hours."""
        await self.bot.wait_until_ready()
        
        # Refresh cache for all guilds that have character forums configured
        for guild in self.bot.guilds:
            forum_ids = self.config.get_character_forums(guild.id)
            if forum_ids:
                await self.build_cache(guild)

    character_group = app_commands.Group(
        name="character",
        description="Character search and configuration"
    )

    async def character_autocomplete(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete function for character names."""
        if not interaction.guild:
            return []
        
        guild_id = interaction.guild.id
        
        # Ensure cache is built for this guild
        if guild_id not in self.thread_cache or not self.thread_cache[guild_id]:
            await self.build_cache(interaction.guild)
        
        # Get all character names from cache for this guild
        cache = self.thread_cache.get(guild_id, [])
        titles = [title for _, title, _ in cache]
        
        # Filter based on current input (case-insensitive substring match)
        current_lower = current.lower()
        matches = [
            title for title in titles
            if current_lower in title.lower()
        ]
        
        # Sort by relevance (exact matches first, then by length)
        matches.sort(key=lambda x: (not x.lower().startswith(current_lower), len(x)))
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=title, value=title)
            for title in matches[:25]
        ]

    @character_group.command(name="search", description="Find a character by name.")
    @app_commands.autocomplete(name=character_autocomplete)
    async def character_search(self, interaction: Interaction, name: str):
        try:
            await interaction.response.defer(thinking=True, ephemeral=False)
        except discord.errors.NotFound:
            # Interaction already expired, can't respond
            return

        if not interaction.guild:
            await interaction.followup.send("❌ This command can only be used in a server.")
            return

        guild_id = interaction.guild.id
        
        # Ensure cache is built
        if guild_id not in self.thread_cache or not self.thread_cache[guild_id]:
            await self.build_cache(interaction.guild)

        cache = self.thread_cache.get(guild_id, [])
        if not cache:
            await interaction.followup.send(
                "❌ No character forums configured for this server. Use `/character add` to add forums."
            )
            return

        titles = {tid: title for tid, title, _ in cache}
        query = name.lower()

        # Step 1: substring match
        substring_hits = [
            (tid, title) for tid, title in titles.items()
            if query in title.lower()
        ]

        if substring_hits:
            thread_id, matched_title = min(substring_hits, key=lambda x: len(x[1]))
        else:
            # Step 2: fuzzy fallback
            best_match = process.extractOne(
                name,
                titles.values(),
                scorer=fuzz.token_set_ratio
            )

            if not best_match or best_match[1] < 80:
                return await interaction.followup.send(
                    f"❌ Couldn't find a close match for **{name}**."
                )

            matched_title = best_match[0]
            thread_id = next(tid for tid, title in titles.items() if title == matched_title)

        # Resolve from cache
        match = next((tid, title, origin) for tid, title, origin in cache if tid == thread_id)
        _, title, origin = match
        jump_url = f"https://discord.com/channels/{interaction.guild.id}/{thread_id}"

        await interaction.followup.send(
            f"🔎 Closest match in **{origin}**: **{title}**\n{jump_url}"
        )

    @character_group.command(name="add", description="Add a forum channel to character search")
    @app_commands.describe(
        forum="The forum channel containing character threads"
    )
    @app_commands.default_permissions(administrator=True)
    async def character_add(self, interaction: Interaction, forum: discord.ForumChannel):
        """Add a character forum for this guild."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Add the character forum
        added = self.config.add_character_forum(interaction.guild.id, forum.id)
        
        if not added:
            await interaction.followup.send(
                f"⚠️ **{forum.name}** is already configured as a character forum.",
                ephemeral=True
            )
            return
        
        # Rebuild cache immediately
        await self.build_cache(interaction.guild)
        
        forums = self.config.get_character_forums(interaction.guild.id)
        await interaction.followup.send(
            f"✅ Added **{forum.name}** to character forums. "
            f"Now caching {len(forums)} forum(s) with {len(self.thread_cache.get(interaction.guild.id, []))} total threads.",
            ephemeral=True
        )
    
    @character_group.command(name="remove", description="Remove a forum channel from character search")
    @app_commands.describe(
        forum="The forum channel to remove from character search"
    )
    @app_commands.default_permissions(administrator=True)
    async def character_remove(self, interaction: Interaction, forum: discord.ForumChannel):
        """Remove a character forum for this guild."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Remove the character forum
        removed = self.config.remove_character_forum(interaction.guild.id, forum.id)
        
        if not removed:
            await interaction.followup.send(
                f"⚠️ **{forum.name}** is not configured as a character forum.",
                ephemeral=True
            )
            return
        
        # Rebuild cache immediately
        await self.build_cache(interaction.guild)
        
        forums = self.config.get_character_forums(interaction.guild.id)
        if forums:
            await interaction.followup.send(
                f"✅ Removed **{forum.name}** from character forums. "
                f"Now caching {len(forums)} forum(s) with {len(self.thread_cache.get(interaction.guild.id, []))} total threads.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Removed **{forum.name}** from character forums. No character forums remaining.",
                ephemeral=True
            )
    
    @character_group.command(name="list", description="List all configured character forums")
    @app_commands.default_permissions(administrator=True)
    async def character_list(self, interaction: Interaction):
        """List all configured character forums for this guild."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        forums = self.config.get_character_forums(interaction.guild.id)
        if not forums:
            await interaction.followup.send(
                "No character forums configured for this guild.",
                ephemeral=True
            )
            return
        
        lines = []
        for forum_id in forums:
            forum = interaction.guild.get_channel(forum_id)
            forum_name = forum.name if forum else f"Unknown ({forum_id})"
            lines.append(f"• **{forum_name}**")
        
        await interaction.followup.send(
            f"**Configured Character Forums ({len(forums)}):**\n" + "\n".join(lines),
            ephemeral=True
        )


async def setup(bot):
    cog = Characters(bot)
    await bot.add_cog(cog)
    # Remove existing command/group if it exists (for reloads)
    try:
        bot.tree.remove_command("character")
        print("[Characters] Removed existing character command")
    except Exception as e:
        print(f"[Characters] No existing character command to remove: {e}")
    # Add the character group
    try:
        bot.tree.add_command(cog.character_group)
        print("[Characters] Successfully added character group")
    except Exception as e:
        print(f"[Characters] ERROR: Failed to add character group: {e}")
        import traceback
        traceback.print_exc()
