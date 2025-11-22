# cogs/move_any.py
# Move command moved to cogs/move.py as part of move group
# This file now only contains EditReaction

import discord
from discord.ext import commands

class EditReaction(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "📝":
            return

        # Safety checks
        if not payload.guild_id:
            return  # DM reactions not supported
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return  # Guild not found (bot may have left)
        
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return  # Channel not found
        
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return  # Can't fetch message
        
        user = guild.get_member(payload.user_id)
        if not user or user.bot:
            return

        # Only allow editing messages inside threads
        if not isinstance(channel, discord.Thread):
            return await user.send("📝 You can only edit messages inside threads.")

        try:
            # Note: Modals can only be sent via interaction responses, not DMs
            # We'll send a message with instructions instead
            await user.send(
                f"📝 You reacted to [this message]({message.jump_url}).\n\n"
                f"**Note:** Message editing via reaction is currently limited. "
                f"To edit this message, you can:\n"
                f"1. Edit the message directly in Discord (if you're the author)\n"
                f"2. Use Discord's built-in edit feature"
            )
        except discord.Forbidden:
            # User has DMs disabled, can't notify them
            pass
        except Exception as e:
            print(f"[EditReaction] Error while handling edit reaction: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(EditReaction(bot))
