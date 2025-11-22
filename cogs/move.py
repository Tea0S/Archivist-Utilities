# cogs/move.py
import discord
from discord.ext import commands
from discord import app_commands
from core.config import settings

class Move(commands.Cog):
    """Commands for moving threads between forums and channels."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    move_group = app_commands.Group(name="move", description="Move threads between forums and channels")

    @move_group.command(name="thread", description="Move the current thread to any target forum or text channel.")
    @app_commands.describe(
        destination="Tag or select the destination forum or text channel.",
        rename="Optionally rename the thread when moving.",
        archive_original="Archive and lock the original thread after moving (default: True)."
    )
    @app_commands.default_permissions(administrator=True)
    async def move_thread(
        self,
        interaction: discord.Interaction,
        destination: discord.abc.GuildChannel,
        rename: str | None = None,
        archive_original: bool = True
    ):
        # Must be used inside a thread
        if not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message(
                "❌ This command must be used inside a thread.", ephemeral=True
            )

        if not isinstance(destination, (discord.ForumChannel, discord.TextChannel)):
            return await interaction.response.send_message(
                "❌ Destination must be a forum or text channel.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True, thinking=True)

        source_thread = interaction.channel
        history = [m async for m in source_thread.history(limit=None, oldest_first=True)]
        if not history:
            return await interaction.followup.send("❌ No messages to move.")

        new_thread = None
        if isinstance(destination, discord.ForumChannel):
            thread_name = rename or source_thread.name
            existing = discord.utils.find(
                lambda t: t.name.strip().lower() == thread_name.strip().lower(),
                destination.threads
            )
            if not existing:
                async for t in destination.archived_threads(limit=None):
                    if t.name.strip().lower() == thread_name.strip().lower():
                        existing = t
                        break

            if existing:
                new_thread = existing
                if new_thread.archived:
                    await new_thread.edit(archived=False, locked=False)

        # Create thread if not found
        if isinstance(destination, discord.ForumChannel) and not new_thread:
            first_msg = history[0]
            files = []
            # ✅ Safe file collection
            for att in first_msg.attachments:
                try:
                    files.append(await att.to_file())
                except Exception:
                    pass

            # ✅ Only include files arg if we actually have files
            create_kwargs = dict(name=rename or source_thread.name, content=first_msg.content or " ")
            if files:
                create_kwargs["files"] = files

            new_thread_obj = await destination.create_thread(**create_kwargs)
            new_thread = new_thread_obj.thread

        elif isinstance(destination, discord.TextChannel):
            first_msg = history[0]
            header = f"**Moved Thread:** {rename or source_thread.name}"
            await destination.send(header)
            new_thread = destination

        # Copy all messages (including attachments)
        for msg in history[1:]:
            content = msg.content or ""
            files = []
            for a in msg.attachments:
                try:
                    files.append(await a.to_file())
                except Exception:
                    pass

            # Split messages if too long
            if len(content) > 2000:
                chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
                for chunk in chunks:
                    await new_thread.send(chunk)
            else:
                if files:
                    await new_thread.send(content or " ", files=files)
                else:
                    await new_thread.send(content or " ")

        # Archive source thread if desired
        if archive_original:
            try:
                await source_thread.edit(archived=True, locked=True)
            except Exception:
                pass

        dest_link = (
            new_thread.jump_url if isinstance(new_thread, discord.Thread) else destination.jump_url
        )
        await interaction.followup.send(
            f"✅ Thread moved to {destination.mention} → {dest_link}", ephemeral=False
        )

    @move_group.command(name="character", description="Move the current thread to another forum (npc, graveyard, characters).")
    @app_commands.describe(
        destination="Use this to move character sheets to the following locations: npc, graveyard, characters",
        played_by="Who played this character (graveyard only)",
        cause_of_death="Cause of death (graveyard only)"
    )
    @app_commands.default_permissions(administrator=True)
    async def move_character(
        self,
        interaction: discord.Interaction,
        destination: str,
        played_by: str = None,
        cause_of_death: str = None
    ):
        # Must be run inside a thread
        if not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message("❌ This command must be used inside a thread.", ephemeral=True)

        # Map destination -> forum
        dest_map = {
            "npc": settings.NPC_BACKSTORIES_CHANNEL_ID,
            "graveyard": settings.CHARACTER_GRAVEYARD_CHANNEL_ID,
            "characters": settings.CHARACTER_BACKSTORIES_CHANNEL_ID,
        }
        dest_id = dest_map.get(destination.lower())
        if not dest_id:
            return await interaction.response.send_message("❌ Invalid destination.", ephemeral=True)

        forum = interaction.guild.get_channel(dest_id)
        if not forum or not isinstance(forum, discord.ForumChannel):
            return await interaction.response.send_message("❌ Destination forum not found.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        # Collect all messages
        source_thread = interaction.channel
        history = [m async for m in source_thread.history(limit=None, oldest_first=True)]
        if not history:
            return await interaction.followup.send("❌ No messages to move.")

        # First message handling
        first_msg = history[0]
        intro_lines = []
        if destination == "graveyard":
            if not played_by or not cause_of_death:
                return await interaction.followup.send("❌ Graveyard moves require `played_by` and `cause_of_death`.")
            intro_lines.append(f"**Played by:** {played_by}")
            intro_lines.append(f"**Cause of death:** {cause_of_death}")

        intro_text = "\n".join(intro_lines) if intro_lines else first_msg.content or ""
        files = []
        if first_msg.attachments:
            for att in first_msg.attachments:
                files.append(await att.to_file())

        # Create new thread in destination
        tw = await forum.create_thread(
            name=source_thread.name,
            content=intro_text or " ",
            files=files if files else None,
        )
        new_thread = tw.thread

        # Copy the rest (only text, no more attachments)
        for msg in history[1:]:
            content = msg.content or ""
            if content:
                if len(content) > 2000:
                    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
                    for chunk in chunks:
                        await new_thread.send(chunk)
                else:
                    await new_thread.send(content)

        await interaction.followup.send(f"✅ Thread moved to {forum.mention}: {new_thread.jump_url}")


async def setup(bot: commands.Bot):
    cog = Move(bot)
    await bot.add_cog(cog)
    # Add command globally, handle if already registered
    try:
        bot.tree.add_command(cog.move_group)
    except app_commands.CommandAlreadyRegistered:
        # Command already registered, skip
        pass

