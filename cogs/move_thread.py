# cogs/move_thread.py
# Move command moved to cogs/move.py as part of move group
# This file is now empty - keeping for potential future use

import discord
from discord.ext import commands

class MoveThread(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

async def setup(bot: commands.Bot):
    await bot.add_cog(MoveThread(bot))
