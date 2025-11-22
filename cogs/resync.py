# cogs/resync.py
# This cog is now empty - resync command moved to admin.py
# Keeping file for potential future use

import discord
from discord.ext import commands

class Resync(commands.Cog):
    """Force-refresh all slash commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

async def setup(bot: commands.Bot):
    await bot.add_cog(Resync(bot))





