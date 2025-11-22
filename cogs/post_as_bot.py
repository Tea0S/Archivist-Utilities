import discord
from discord.ext import commands
from core.config import settings
from core.utils import is_owner_or_admin

PENCIL_EMOJI = "✏️"  # :pencil2:

class PostAsBot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots or DMs
        if message.author.bot or not message.guild:
            return

        # must start with :pencil2: and have admin perms (or be owner)
        if not message.content.startswith(PENCIL_EMOJI):
            return
        if not is_owner_or_admin(message.author):
            await message.reply("❌ Only administrators can post as the bot.", delete_after=5)
            return

        # remove trigger emoji
        content = message.content[len(PENCIL_EMOJI):].strip()
        if not content and not message.attachments:
            await message.reply("✏️ Please include text or an attachment to post.", delete_after=5)
            return

        try:
            # collect any attached files
            files = [await a.to_file() for a in message.attachments]

            # send message as bot
            sent = await message.channel.send(content=content or " ", files=files or None)
            print(f"[✏️ PostAsBot] {message.author.display_name} posted as bot in {message.channel.name}")

            # delete original admin message
            await message.delete()
        except discord.Forbidden:
            await message.reply("❌ I don't have permission to post here.", delete_after=5)
        except Exception as e:
            print(f"[✏️ PostAsBot] Error: {e}")
            await message.reply(f"❌ Failed to post as bot: {e}", delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(PostAsBot(bot))
    print("[✏️ PostAsBot] Cog loaded successfully.")
