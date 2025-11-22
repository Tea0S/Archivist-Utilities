# cogs/bot_customization.py

import json
import os
import logging
import io
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

log = logging.getLogger(__name__)

# Configuration file path
CONFIG_FILE = "data/bot_customization.json"


class BotCustomizationConfig:
    """Manages per-server bot customization settings stored in JSON."""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self._ensure_config_file()
    
    def _ensure_config_file(self):
        """Ensure the config file and directory exist."""
        dir_path = os.path.dirname(self.config_file)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        if not os.path.exists(self.config_file):
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"guilds": {}}, f, indent=2)
    
    def _load(self) -> dict:
        """Load configuration from file."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "guilds" not in data:
                    data["guilds"] = {}
                return data
        except Exception:
            return {"guilds": {}}
    
    def _save(self, data: dict):
        """Save configuration to file."""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_guild_config(self, guild_id: int) -> dict:
        """Get configuration for a specific guild."""
        data = self._load()
        guild_str = str(guild_id)
        if guild_str not in data["guilds"]:
            data["guilds"][guild_str] = {
                "nickname": None,
                "avatar_url": None
            }
            self._save(data)
        return data["guilds"][guild_str]
    
    def set_nickname(self, guild_id: int, nickname: Optional[str]):
        """Set nickname preference for a guild."""
        data = self._load()
        guild_str = str(guild_id)
        if guild_str not in data["guilds"]:
            data["guilds"][guild_str] = {}
        data["guilds"][guild_str]["nickname"] = nickname
        self._save(data)
    
    def set_avatar_url(self, guild_id: int, avatar_url: Optional[str]):
        """Set avatar URL preference for a guild."""
        data = self._load()
        guild_str = str(guild_id)
        if guild_str not in data["guilds"]:
            data["guilds"][guild_str] = {}
        data["guilds"][guild_str]["avatar_url"] = avatar_url
        self._save(data)
    
    def get_nickname(self, guild_id: int) -> Optional[str]:
        """Get stored nickname preference for a guild."""
        config = self.get_guild_config(guild_id)
        return config.get("nickname")
    
    def get_avatar_url(self, guild_id: int) -> Optional[str]:
        """Get stored avatar URL preference for a guild."""
        config = self.get_guild_config(guild_id)
        return config.get("avatar_url")


class BotCustomization(commands.Cog):
    """Cog for managing per-server bot customization (nickname and avatar)."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = BotCustomizationConfig()
    
    # Create command group
    customization_group = app_commands.Group(
        name="bot",
        description="Manage bot customization settings for this server"
    )
    
    @customization_group.command(name="nickname", description="Set or reset the bot's nickname for this server")
    @app_commands.describe(
        nickname="The new nickname for the bot (leave empty to reset to default)"
    )
    @app_commands.default_permissions(administrator=True)
    async def bot_nickname(
        self,
        interaction: discord.Interaction,
        nickname: Optional[str] = None
    ):
        """Set or reset the bot's nickname for this server."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the bot's member object in this guild
            me = interaction.guild.me
            
            if nickname is None or nickname.strip() == "":
                # Reset nickname to None (defaults to bot username)
                await me.edit(nick=None)
                self.config.set_nickname(interaction.guild.id, None)
                await interaction.followup.send(
                    f"✅ Bot nickname reset to default: **{self.bot.user.name}**",
                    ephemeral=True
                )
                log.info(f"Bot nickname reset in guild {interaction.guild.id} by {interaction.user}")
            else:
                # Set new nickname
                nickname = nickname.strip()
                if len(nickname) > 32:
                    await interaction.followup.send(
                        "❌ Nickname is too long (maximum 32 characters).",
                        ephemeral=True
                    )
                    return
                
                await me.edit(nick=nickname)
                self.config.set_nickname(interaction.guild.id, nickname)
                await interaction.followup.send(
                    f"✅ Bot nickname set to: **{nickname}**",
                    ephemeral=True
                )
                log.info(f"Bot nickname set to '{nickname}' in guild {interaction.guild.id} by {interaction.user}")
                
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to change my nickname. Please ensure I have the 'Change Nickname' permission.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to change nickname: {e}",
                ephemeral=True
            )
            log.error(f"Failed to change bot nickname: {e}")
        except Exception as e:
            await interaction.followup.send(
                f"❌ An unexpected error occurred: {e}",
                ephemeral=True
            )
            log.exception(f"Unexpected error changing bot nickname: {e}")
    
    @customization_group.command(name="avatar", description="Set the bot's guild avatar for this server")
    @app_commands.describe(
        url="URL of the avatar image",
        attachment="Image file to use as avatar (alternative to URL)",
        apply="Whether to immediately apply this avatar (default: true). Set to false to just save the preference."
    )
    @app_commands.default_permissions(administrator=True)
    async def bot_avatar(
        self,
        interaction: discord.Interaction,
        url: Optional[str] = None,
        attachment: Optional[discord.Attachment] = None,
        apply: bool = True
    ):
        """Set the bot's guild avatar for this server.
        
        This sets a per-server (guild) avatar that appears in this server's member list.
        Each server can have its own avatar independent of other servers.
        Note: This feature may require Discord API support for guild avatars.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            avatar_bytes = None
            source_info = None
            
            if attachment:
                # Use uploaded attachment (always applies immediately, can't save for later)
                if not attachment.content_type or not attachment.content_type.startswith('image/'):
                    await interaction.followup.send(
                        "❌ The attachment must be an image file.",
                        ephemeral=True
                    )
                    return
                
                if attachment.size > 8 * 1024 * 1024:
                    await interaction.followup.send(
                        "❌ Image file is too large (maximum 8MB).",
                        ephemeral=True
                    )
                    return
                
                avatar_bytes = await attachment.read()
                source_info = "uploaded_file"
                
                # Uploaded files can't be saved for later (we don't store the bytes)
                # Always apply them immediately
                if not apply:
                    await interaction.followup.send(
                        "⚠️ Uploaded files can only be applied immediately (not saved for later).\n"
                        "To save a preference, provide a URL instead. Applying this avatar now...",
                        ephemeral=True
                    )
                    apply = True
                
            elif url:
                # Download from URL
                import httpx
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    response = await client.get(url)
                    if response.status_code != 200:
                        await interaction.followup.send(
                            f"❌ Failed to download image from URL (status {response.status_code})",
                            ephemeral=True
                        )
                        return
                    avatar_bytes = response.content
                    source_info = url
                    
            else:
                await interaction.followup.send(
                    "❌ Please provide either a URL or upload an image file.",
                    ephemeral=True
                )
                return
            
            # Validate image size (Discord limit is 8MB) - already checked for attachments
            if not attachment and len(avatar_bytes) > 8 * 1024 * 1024:
                await interaction.followup.send(
                    "❌ Image file is too large (maximum 8MB).",
                    ephemeral=True
                )
                return
            
            # Validate that it's a valid image by attempting to open it (optional validation)
            # Note: Discord will also validate the image, but this provides early feedback
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(avatar_bytes))
                img.verify()  # Verify it's a valid image
                img.close()
            except ImportError:
                # PIL/Pillow not installed, skip image validation
                # Discord will validate the image format when we try to set it
                pass
            except Exception as e:
                log.warning(f"Image validation failed (may still work): {e}")
                # Continue anyway - Discord will validate
                pass
            
            # Store preference for this guild (always store, even if not applying)
            avatar_pref = url if url else (source_info if source_info else "uploaded_file")
            self.config.set_avatar_url(interaction.guild.id, avatar_pref)
            
            if apply:
                # Apply the guild avatar (per-server avatar)
                me = interaction.guild.me
                try:
                    # Try using Member.edit() to set guild avatar
                    await me.edit(avatar=avatar_bytes)
                    
                    await interaction.followup.send(
                        f"✅ Guild avatar set for **{interaction.guild.name}**!\n"
                        f"🎉 This avatar will appear in this server's member list.",
                        ephemeral=True
                    )
                    log.info(f"Guild avatar updated in guild {interaction.guild.id} by {interaction.user}")
                except (discord.HTTPException, TypeError, AttributeError) as e:
                    # Log the actual error to see what's happening
                    log.warning(f"Failed to set guild avatar via Member.edit(): {type(e).__name__}: {e}")
                    # Fallback: if guild avatar not supported, try global avatar
                    try:
                        await self.bot.user.edit(avatar=avatar_bytes)
                        await interaction.followup.send(
                            f"✅ Avatar preference saved and applied for **{interaction.guild.name}**!\n"
                            f"⚠️ **Note:** Guild avatars may not be supported (error: {type(e).__name__}). This changes the bot's global avatar, which is visible in all servers.",
                            ephemeral=True
                        )
                        log.info(f"Bot global avatar updated in guild {interaction.guild.id} by {interaction.user} (guild avatar failed: {type(e).__name__}: {e})")
                    except Exception as e2:
                        raise e2
            else:
                # Just save preference without applying
                await interaction.followup.send(
                    f"✅ Avatar preference saved for **{interaction.guild.name}**.\n"
                    f"Use `/bot avatar apply` to apply it (this will change the global avatar).",
                    ephemeral=True
                )
                log.info(f"Bot avatar preference saved (not applied) in guild {interaction.guild.id} by {interaction.user}")
            
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to update avatar: {e}",
                ephemeral=True
            )
            log.error(f"Failed to update bot avatar: {e}")
        except Exception as e:
            await interaction.followup.send(
                f"❌ An unexpected error occurred: {e}",
                ephemeral=True
            )
            log.exception(f"Unexpected error updating bot avatar: {e}")


async def setup(bot: commands.Bot):
    cog = BotCustomization(bot)
    await bot.add_cog(cog)
    
    # Remove existing command/group if it exists (for reloads)
    try:
        bot.tree.remove_command("bot")
        print("[BotCustomization] Removed existing bot command")
    except Exception as e:
        print(f"[BotCustomization] No existing bot command to remove: {e}")
    
    # Add the command group
    try:
        bot.tree.add_command(cog.customization_group)
        print("[BotCustomization] Successfully added bot customization command group")
    except Exception as e:
        print(f"[BotCustomization] ERROR: Failed to add bot customization command group: {e}")
        import traceback
        traceback.print_exc()
    
    print("[BotCustomization] Successfully loaded bot customization cog")

