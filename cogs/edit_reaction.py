import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from core.config import settings

class EditReaction(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_edits = {}  # user_id: {guild_id, channel_id, message_id, expires_at}
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    # --- reaction listener ---
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # only respond to ✏️
        if str(payload.emoji) != "✏️" or payload.user_id == self.bot.user.id:
            return

        try:
            guild = await self.bot.fetch_guild(payload.guild_id)
            channel = await self.bot.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            user = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        except Exception as e:
            print(f"[✏️ EditReaction] Fetch error: {e}")
            return

        # ✅ restrict to threads only
        if not isinstance(channel, discord.Thread):
            return

        # ✅ restrict to administrators only
        if not user.guild_permissions.administrator:
            try:
                await channel.send(
                    f"{user.mention}, you must be an **administrator** to edit messages this way."
                )
            except Exception:
                pass
            return

        try:
            dm = await user.create_dm()
            preview = message.content[:1000] if message.content else "(no text)"
            await dm.send(
                f"✏️ You reacted to a message in **{channel.name}**.\n"
                f"Original message:\n```\n{preview}\n```"
                "\nReply here with your **new message content**."
                "\nYou have **15 minutes** before this edit session expires."
            )

            self.active_edits[user.id] = {
                "guild_id": guild.id,
                "channel_id": channel.id,
                "message_id": message.id,
                "emoji": payload.emoji.name,
                "expires_at": datetime.utcnow() + timedelta(minutes=15),
            }

            print(f"[✏️ EditReaction] Edit session started for {user.display_name} in {channel.name}")

        except discord.Forbidden:
            print(f"[✏️ EditReaction] Cannot DM {user.display_name}")
            try:
                await channel.send(
                    f"{user.mention}, I couldn’t DM you to edit that post. Please enable DMs from server members."
                )
            except Exception:
                pass

    # --- message listener for DM replies ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild:
            return  # ignore bots and guild messages

        edit_info = self.active_edits.get(message.author.id)
        if not edit_info:
            return

        # Check expiration
        if datetime.utcnow() > edit_info["expires_at"]:
            await message.channel.send(
                "⌛ This edit session has expired after 15 minutes. React again with ✏️ if you still need to edit."
            )
            self.active_edits.pop(message.author.id, None)
            return

        new_content = message.content.strip()
        if not new_content:
            await message.channel.send("❌ Edit canceled — message cannot be empty.")
            self.active_edits.pop(message.author.id, None)
            return

        try:
            guild = await self.bot.fetch_guild(edit_info["guild_id"])
            channel = await self.bot.fetch_channel(edit_info["channel_id"])
            target_message = await channel.fetch_message(edit_info["message_id"])

            await target_message.edit(content=new_content)
            await message.channel.send("✅ Your edit has been applied successfully!")

            # ✅ Remove the ✏️ reaction from the original message
            try:
                for reaction in target_message.reactions:
                    if str(reaction.emoji) == edit_info["emoji"]:
                        async for user in reaction.users():
                            if user.id == message.author.id:
                                await target_message.remove_reaction(edit_info["emoji"], user)
                                break
            except Exception as e:
                print(f"[✏️ EditReaction] Could not remove reaction: {e}")

            print(f"[✏️ EditReaction] {message.author.display_name} edited a message in {channel.name}")

        except Exception as e:
            await message.channel.send(f"❌ Failed to edit the message: {e}")
            print(f"[✏️ EditReaction] Edit failed: {e}")

        # clean up
        self.active_edits.pop(message.author.id, None)

    # --- cleanup expired sessions ---
    @tasks.loop(minutes=1)
    async def cleanup_task(self):
        now = datetime.utcnow()
        expired_users = [uid for uid, info in self.active_edits.items() if info["expires_at"] < now]
        for uid in expired_users:
            try:
                user = self.bot.get_user(uid)
                if user:
                    await user.send("⌛ Your ✏️ edit session has expired after 15 minutes.")
            except Exception:
                pass
            self.active_edits.pop(uid, None)
        if expired_users:
            print(f"[✏️ EditReaction] Cleaned up {len(expired_users)} expired edit sessions.")

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(EditReaction(bot))
    print("[✏️ EditReaction] Cog loaded successfully.")
