# cogs/dice_challenges.py

import json
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from cogs.index_manager import IndexConfig
from rapidfuzz import fuzz, process
from core.utils import is_owner_or_admin

# Data file paths
CHALLENGES_DATA_FILE = Path("data/dice_challenges.json")
CONFIG_FILE = Path("data/dice_challenges_config.json")

class DiceChallenges(commands.Cog):
    """Manage dice challenge results and win/loss streaks."""
    
    # Admin command group - must be defined at class level
    challenge_group = app_commands.Group(
        name="challenge",
        description="Dice challenge management commands",
        default_permissions=discord.Permissions(administrator=True)
    )
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = IndexConfig()
        self.thread_cache = {}  # Cache for character threads
        self._button_posted = {}  # Track if we've posted the button per guild
        self._ensure_data_file()
        self._ensure_config_file()
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when bot is ready - post button if needed."""
        # Wait a bit for channels to be available
        await asyncio.sleep(3)
        
        # Check all guilds for configured button channels
        config = self._load_config()
        for guild_id_str, guild_config in config.items():
            try:
                guild_id = int(guild_id_str)
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                button_channel_id = guild_config.get("button_channel_id")
                if not button_channel_id:
                    continue
                
                # Skip if we've already posted this session
                if self._button_posted.get(guild_id, False):
                    continue
                
                channel = guild.get_channel(button_channel_id)
                if not channel:
                    print(f"[DiceChallenges] Channel {button_channel_id} not found in guild {guild_id}")
                    continue
                
                # Check if button already exists
                button_exists = False
                async for message in channel.history(limit=100):
                    if message.author == self.bot.user:
                        if "🎲 Finish Dice Challenge" in message.content:
                            if message.components:
                                button_exists = True
                                break
                        elif message.components:
                            for row in message.components:
                                for item in row.children:
                                    if isinstance(item, discord.ui.Button) and item.custom_id == "finish_challenge_btn":
                                        button_exists = True
                                        break
                                if button_exists:
                                    break
                            if button_exists:
                                break
                
                if button_exists:
                    print(f"[DiceChallenges] Button already exists in channel {button_channel_id} for guild {guild_id}")
                    self._button_posted[guild_id] = True
                    continue
                
                # Post the button
                view = FinishChallengeView(self.bot, self)
                await channel.send(
                    "**🎲 Finish Dice Challenge**\n"
                    "Click the button below to record a completed dice challenge.",
                    view=view
                )
                print(f"[DiceChallenges] Posted finish challenge button to channel {button_channel_id} in guild {guild_id}")
                self._button_posted[guild_id] = True
            except Exception as e:
                print(f"[DiceChallenges] Failed to post button for guild {guild_id_str}: {e}")
    
    def _ensure_data_file(self):
        """Ensure the data file exists."""
        CHALLENGES_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not CHALLENGES_DATA_FILE.exists():
            with open(CHALLENGES_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
    
    def _ensure_config_file(self):
        """Ensure the config file exists."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
    
    def _load_config(self) -> Dict:
        """Load configuration from file."""
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_config(self, config: Dict):
        """Save configuration to file."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    
    def get_guild_config(self, guild_id: int) -> Dict:
        """Get configuration for a specific guild."""
        config = self._load_config()
        guild_key = str(guild_id)
        if guild_key not in config:
            return {
                "button_channel_id": None,
                "approval_channel_id": None,
                "approvals_enabled": True,  # Default to enabled
                "message_header": "## 🎲 Dice Challenge Results",
                "message_fields": ["current_streak", "total_wins", "total_losses", "total_games", "streak_warning"]
            }
        guild_config = config[guild_key]
        # Ensure message config exists
        if "message_header" not in guild_config:
            guild_config["message_header"] = "## 🎲 Dice Challenge Results"
        if "message_fields" not in guild_config:
            guild_config["message_fields"] = ["current_streak", "total_wins", "total_losses", "total_games", "streak_warning"]
        return guild_config
    
    def set_guild_config(self, guild_id: int, **kwargs):
        """Update configuration for a specific guild."""
        config = self._load_config()
        guild_key = str(guild_id)
        if guild_key not in config:
            config[guild_key] = {
                "button_channel_id": None,
                "approval_channel_id": None,
                "approvals_enabled": True
            }
        
        for key, value in kwargs.items():
            config[guild_key][key] = value
        
        self._save_config(config)
    
    def _load_data(self) -> Dict:
        """Load challenge data from file."""
        try:
            with open(CHALLENGES_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_data(self, data: Dict):
        """Save challenge data to file."""
        with open(CHALLENGES_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    async def _build_thread_cache(self, guild: discord.Guild):
        """Build cache of character threads for autocomplete."""
        guild_id = guild.id
        if guild_id in self.thread_cache:
            return
        
        self.thread_cache[guild_id] = []
        forum_ids = self.config.get_character_forums(guild_id)
        if not forum_ids:
            return
        
        for forum_id in forum_ids:
            forum = guild.get_channel(forum_id)
            if not forum or not isinstance(forum, discord.ForumChannel):
                continue
            
            threads = list(forum.threads)
            async for t in forum.archived_threads(limit=None):
                threads.append(t)
            
            for thread in threads:
                if "index" in thread.name.lower():
                    continue
                self.thread_cache[guild_id].append((thread.id, thread.name, forum.name))
    
    async def _get_character_names(self, guild: discord.Guild) -> List[str]:
        """Get list of character names for autocomplete."""
        await self._build_thread_cache(guild)
        cache = self.thread_cache.get(guild.id, [])
        return [title for _, title, _ in cache]
    
    async def _find_character_thread(self, guild: discord.Guild, character_name: str) -> Optional[discord.Thread]:
        """Find a character thread by name."""
        await self._build_thread_cache(guild)
        cache = self.thread_cache.get(guild.id, [])
        if not cache:
            return None
        
        titles = {tid: title for tid, title, _ in cache}
        query = character_name.lower()
        
        # Try substring match first
        substring_hits = [
            (tid, title) for tid, title in titles.items()
            if query in title.lower()
        ]
        
        if substring_hits:
            thread_id, _ = min(substring_hits, key=lambda x: len(x[1]))
        else:
            # Fuzzy fallback
            best_match = process.extractOne(
                character_name,
                titles.values(),
                scorer=fuzz.token_set_ratio
            )
            
            if not best_match or best_match[1] < 80:
                return None
            
            matched_title = best_match[0]
            thread_id = next(tid for tid, title in titles.items() if title == matched_title)
        
        return guild.get_thread(thread_id)
    
    def _get_streaks(self, character_name: str) -> Dict[str, int]:
        """Get win/loss streaks for a character."""
        data = self._load_data()
        char_data = data.get(character_name, {})
        return {
            "wins": char_data.get("wins", 0),
            "losses": char_data.get("losses", 0),
            "current_win_streak": char_data.get("current_win_streak", 0),
            "current_loss_streak": char_data.get("current_loss_streak", 0),
            "total_games": char_data.get("total_games", 0)
        }
    
    def _record_result(self, winner: str, loser: str):
        """Record a challenge result and update streaks."""
        data = self._load_data()
        
        # Initialize if needed
        if winner not in data:
            data[winner] = {
                "wins": 0,
                "losses": 0,
                "current_win_streak": 0,
                "current_loss_streak": 0,
                "total_games": 0,
                "game_history": []
            }
        
        if loser not in data:
            data[loser] = {
                "wins": 0,
                "losses": 0,
                "current_win_streak": 0,
                "current_loss_streak": 0,
                "total_games": 0,
                "game_history": []
            }
        
        # Create game record
        game_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "opponent": loser,
            "result": "win"
        }
        
        loser_game_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "opponent": winner,
            "result": "loss"
        }
        
        # Update winner
        data[winner]["wins"] += 1
        data[winner]["current_win_streak"] += 1
        data[winner]["current_loss_streak"] = 0  # Reset loss streak
        data[winner]["total_games"] += 1
        data[winner]["game_history"].append(game_record)
        # Keep only last 10 games
        data[winner]["game_history"] = data[winner]["game_history"][-10:]
        
        # Update loser
        data[loser]["losses"] += 1
        data[loser]["current_loss_streak"] += 1
        data[loser]["current_win_streak"] = 0  # Reset win streak
        data[loser]["total_games"] += 1
        data[loser]["game_history"].append(loser_game_record)
        # Keep only last 10 games
        data[loser]["game_history"] = data[loser]["game_history"][-10:]
        
        self._save_data(data)
    
    async def _post_to_character_thread(self, thread: discord.Thread, character_name: str, streaks: Dict[str, int]):
        """Post streak update to character thread. Tries to edit last message, falls back to delete and repost."""
        if not thread.guild:
            return
        
        # Get guild-specific message configuration
        guild_config = self.get_guild_config(thread.guild.id)
        header = guild_config.get("message_header", "## 🎲 Dice Challenge Results")
        enabled_fields = guild_config.get("message_fields", ["current_streak", "total_wins", "total_losses", "total_games", "streak_warning"])
        
        win_streak = streaks["current_win_streak"]
        loss_streak = streaks["current_loss_streak"]
        total_wins = streaks["wins"]
        total_losses = streaks["losses"]
        total_games = streaks["total_games"]
        
        # Build message based on configuration
        lines = [header, ""]
        
        # Field mappings
        field_content = {
            "current_streak": None,  # Will be set based on win/loss
            "total_wins": f"**Total Wins:** {total_wins}",
            "total_losses": f"**Total Losses:** {total_losses}",
            "total_games": f"**Total Games:** {total_games}",
            "streak_warning": None  # Will be set based on loss streak
        }
        
        # Set current streak based on win/loss
        if win_streak > 0:
            field_content["current_streak"] = f"**Current Win Streak:** {win_streak} {'win' if win_streak == 1 else 'wins'}"
        elif loss_streak > 0:
            field_content["current_streak"] = f"**Current Loss Streak:** {loss_streak} {'loss' if loss_streak == 1 else 'losses'}"
        else:
            field_content["current_streak"] = None  # No streak
        
        # Set streak warning
        if loss_streak >= 3:
            if loss_streak == 3:
                field_content["streak_warning"] = "⚠️ **Three losses in a row** - Major consequence applies!"
            elif loss_streak >= 4:
                field_content["streak_warning"] = "⚠️ **Four or more losses in a row** - Severe consequence applies!"
        
        # Add enabled fields in order
        for field in enabled_fields:
            if field in field_content and field_content[field]:
                lines.append(field_content[field])
        
        message = "\n".join(lines)
        
        # Load data to check for last message ID
        data = self._load_data()
        char_data = data.get(character_name, {})
        last_message_id = char_data.get("last_message_id")
        
        # Try to edit existing message first
        if last_message_id:
            try:
                last_message = await thread.fetch_message(last_message_id)
                # Check if it's from this bot and contains the header
                if last_message.author == self.bot.user and header in last_message.content:
                    await last_message.edit(content=message)
                    print(f"[DiceChallenges] Edited existing message in thread {thread.id} for {character_name}")
                    return
            except discord.NotFound:
                # Message was deleted, try to delete from our records and post new
                print(f"[DiceChallenges] Last message not found, will delete and repost")
            except discord.Forbidden:
                # Can't edit, try to delete and repost
                print(f"[DiceChallenges] Can't edit message, will delete and repost")
            except Exception as e:
                print(f"[DiceChallenges] Error editing message: {e}, will delete and repost")
            
            # If we get here, editing failed - try to delete the old message
            try:
                if last_message_id:
                    # Try to fetch and delete
                    try:
                        old_message = await thread.fetch_message(last_message_id)
                        if old_message.author == self.bot.user:
                            await old_message.delete()
                            print(f"[DiceChallenges] Deleted old message in thread {thread.id}")
                    except discord.NotFound:
                        pass  # Already deleted, that's fine
            except Exception as e:
                print(f"[DiceChallenges] Error deleting old message: {e}")
        
        # Post new message
        try:
            new_message = await thread.send(message)
            # Save the message ID
            if character_name not in data:
                data[character_name] = {}
            data[character_name]["last_message_id"] = new_message.id
            self._save_data(data)
            print(f"[DiceChallenges] Posted new message in thread {thread.id} for {character_name}")
        except Exception as e:
            print(f"[DiceChallenges] Failed to post to thread {thread.id}: {e}")
    
    async def _send_approval_request(self, challenger1: str, challenger2: str, winner: str, loser: str, thread1: discord.Thread, thread2: discord.Thread, submitted_by: discord.Member):
        """Send challenge result to approval channel."""
        if not submitted_by.guild:
            return None
        
        guild_config = self.get_guild_config(submitted_by.guild.id)
        
        # Check if approvals are enabled
        if not guild_config.get("approvals_enabled", True):
            # Approvals disabled - process immediately
            self._record_result(winner, loser)
            winner_streaks = self._get_streaks(winner)
            loser_streaks = self._get_streaks(loser)
            await self._post_to_character_thread(thread1, winner, winner_streaks)
            await self._post_to_character_thread(thread2, loser, loser_streaks)
            return None
        
        approval_channel_id = guild_config.get("approval_channel_id")
        if not approval_channel_id:
            print(f"[DiceChallenges] Approval channel not configured for guild {submitted_by.guild.id}")
            return None
        
        channel = submitted_by.guild.get_channel(approval_channel_id)
        if not channel:
            print(f"[DiceChallenges] Approval channel {approval_channel_id} not found")
            return None
        
        # Build embed
        embed = discord.Embed(
            title="🎲 Dice Challenge - Pending Approval",
            color=discord.Color.orange(),
            description=f"**Challenger 1:** {challenger1}\n**Challenger 2:** {challenger2}\n\n**Winner:** {winner}\n**Loser:** {loser}",
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Submitted by", value=f"{submitted_by.mention} ({submitted_by.display_name})", inline=False)
        embed.add_field(name="Character Threads", value=f"[{challenger1}]({thread1.jump_url})\n[{challenger2}]({thread2.jump_url})", inline=False)
        
        # Create approval view
        view = ApprovalView(self.bot, self, challenger1, challenger2, winner, loser, thread1, thread2, submitted_by.id)
        
        try:
            message = await channel.send(embed=embed, view=view)
            return message
        except Exception as e:
            print(f"[DiceChallenges] Failed to send approval request: {e}")
            return None
    
    @challenge_group.command(name="adjust", description="Manually adjust a character's challenge record")
    @app_commands.describe(character="Character name to adjust")
    @app_commands.default_permissions(administrator=True)
    async def adjust_record(self, interaction: Interaction, character: str):
        """Manually adjust a character's challenge record."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        # Find the character thread to get exact name
        thread = await self._find_character_thread(interaction.guild, character)
        if not thread:
            await interaction.response.send_message(f"❌ Could not find character **{character}**.", ephemeral=True)
            return
        
        character_name = thread.name
        
        # Load current data to show in modal
        data = self._load_data()
        if character_name not in data:
            data[character_name] = {
                "wins": 0,
                "losses": 0,
                "current_win_streak": 0,
                "current_loss_streak": 0,
                "total_games": 0,
                "game_history": []
            }
        
        current = data[character_name]
        
        # Create and show modal
        modal = AdjustRecordModal(self.bot, self, character_name, current)
        await interaction.response.send_modal(modal)
    
    @challenge_group.command(name="view", description="View a character's challenge record")
    @app_commands.describe(character="Character name to view")
    @app_commands.default_permissions(administrator=True)
    async def view_record(self, interaction: Interaction, character: str):
        """View a character's challenge record (available to everyone)."""
        await interaction.response.defer(ephemeral=True)
        
        # Find the character thread to get exact name
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        thread = await self._find_character_thread(interaction.guild, character)
        if not thread:
            await interaction.followup.send(f"❌ Could not find character **{character}**.", ephemeral=True)
            return
        
        character_name = thread.name
        streaks = self._get_streaks(character_name)
        
        # Get game history
        data = self._load_data()
        char_data = data.get(character_name, {})
        game_history = char_data.get("game_history", [])
        
        # Build response
        lines = [
            f"**📊 {character_name} - Challenge Record**\n",
            f"**Wins:** {streaks['wins']}",
            f"**Losses:** {streaks['losses']}",
            f"**Current Win Streak:** {streaks['current_win_streak']}",
            f"**Current Loss Streak:** {streaks['current_loss_streak']}",
            f"**Total Games:** {streaks['total_games']}",
        ]
        
        # Add game history
        if game_history:
            lines.append("\n**Last 10 Games:**")
            # Sort by timestamp (most recent first)
            sorted_history = sorted(game_history, key=lambda x: x.get("timestamp", ""), reverse=True)
            for i, game in enumerate(sorted_history[:10], 1):
                opponent = game.get("opponent", "Unknown")
                result = game.get("result", "unknown")
                result_emoji = "✅" if result == "win" else "❌"
                result_text = "Won" if result == "win" else "Lost"
                lines.append(f"{i}. {result_emoji} {result_text} against **{opponent}**")
        else:
            lines.append("\n**Game History:** No games recorded yet.")
        
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    
    @challenge_group.command(name="reset", description="Reset a character's challenge record to zero")
    @app_commands.describe(character="Character name to reset")
    @app_commands.default_permissions(administrator=True)
    async def reset_record(self, interaction: Interaction, character: str):
        """Reset a character's challenge record."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Find the character thread to get exact name
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        thread = await self._find_character_thread(interaction.guild, character)
        if not thread:
            await interaction.followup.send(f"❌ Could not find character **{character}**.", ephemeral=True)
            return
        
        character_name = thread.name
        
        # Load and reset data
        data = self._load_data()
        data[character_name] = {
            "wins": 0,
            "losses": 0,
            "current_win_streak": 0,
            "current_loss_streak": 0,
            "total_games": 0,
            "game_history": []
        }
        self._save_data(data)
        
        await interaction.followup.send(
            f"✅ Reset **{character_name}**'s challenge record to zero.",
            ephemeral=True
        )
    
    @challenge_group.command(name="set_channel", description="Configure challenge channels for this server")
    @app_commands.describe(
        button_channel="Channel where the finish challenge button will appear",
        approval_channel="Channel where challenge results are sent for approval",
        approvals_enabled="Whether to require admin approval before posting results"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_channel(
        self,
        interaction: Interaction,
        button_channel: Optional[discord.TextChannel] = None,
        approval_channel: Optional[discord.TextChannel] = None,
        approvals_enabled: Optional[bool] = None
    ):
        """Configure challenge channels for this server."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        updates = []
        current_config = self.get_guild_config(interaction.guild.id)
        
        # Update button channel
        if button_channel is not None:
            self.set_guild_config(interaction.guild.id, button_channel_id=button_channel.id)
            updates.append(f"✅ Button channel set to {button_channel.mention}")
            
            # Post button if channel is set
            try:
                # Check if button already exists
                button_exists = False
                async for message in button_channel.history(limit=100):
                    if message.author == self.bot.user:
                        if "🎲 Finish Dice Challenge" in message.content and message.components:
                            button_exists = True
                            break
                
                if not button_exists:
                    view = FinishChallengeView(self.bot, self)
                    await button_channel.send(
                        "**🎲 Finish Dice Challenge**\n"
                        "Click the button below to record a completed dice challenge.",
                        view=view
                    )
                    updates.append(f"✅ Posted finish challenge button to {button_channel.mention}")
                    self._button_posted[interaction.guild.id] = True
            except Exception as e:
                updates.append(f"⚠️ Failed to post button: {e}")
        
        # Update approval channel
        if approval_channel is not None:
            self.set_guild_config(interaction.guild.id, approval_channel_id=approval_channel.id)
            updates.append(f"✅ Approval channel set to {approval_channel.mention}")
        
        # Update approvals enabled (only if provided)
        if approvals_enabled is not None:
            self.set_guild_config(interaction.guild.id, approvals_enabled=approvals_enabled)
            status = "enabled" if approvals_enabled else "disabled"
            updates.append(f"✅ Approvals {status}")
        
        # Get updated config for display
        config = self.get_guild_config(interaction.guild.id)
        button_ch = interaction.guild.get_channel(config.get("button_channel_id")) if config.get("button_channel_id") else None
        approval_ch = interaction.guild.get_channel(config.get("approval_channel_id")) if config.get("approval_channel_id") else None
        
        if not updates:
            response = "ℹ️ No changes made.\n\n"
        else:
            response = "\n".join(updates) + "\n\n"
        
        response += "**Current Configuration:**\n"
        response += f"Button Channel: {button_ch.mention if button_ch else 'Not set'}\n"
        response += f"Approval Channel: {approval_ch.mention if approval_ch else 'Not set'}\n"
        response += f"Approvals: {'Enabled' if config.get('approvals_enabled', True) else 'Disabled'}"
        
        await interaction.followup.send(response, ephemeral=True)
    
    @challenge_group.command(name="configure_message", description="Configure the format of challenge result messages")
    @app_commands.default_permissions(administrator=True)
    async def configure_message(self, interaction: Interaction):
        """Configure the format of challenge result messages."""
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message("❌ This command requires administrator permissions.", ephemeral=True)
            return
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        # Get current config
        config = self.get_guild_config(interaction.guild.id)
        current_header = config.get("message_header", "## 🎲 Dice Challenge Results")
        current_fields = config.get("message_fields", ["current_streak", "total_wins", "total_losses", "total_games", "streak_warning"])
        
        # Create configuration view
        view = MessageConfigView(self.bot, self, current_header, current_fields)
        
        field_labels = {
            "current_streak": "Current Streak (Win/Loss)",
            "total_wins": "Total Wins",
            "total_losses": "Total Losses",
            "total_games": "Total Games",
            "streak_warning": "Streak Warning (3+ losses)"
        }
        current_field_labels = [field_labels.get(f, f) for f in current_fields]
        
        await interaction.response.send_message(
            "**Configure Challenge Result Message Format**\n\n"
            f"**Current Header:** {current_header}\n"
            f"**Current Fields:** {', '.join(current_field_labels)}\n\n"
            "Click field buttons to toggle them on/off. Click 'Edit Header' to customize the header text, then 'Save Configuration' when done.",
            view=view,
            ephemeral=True
        )


class ChallengerInputModal(discord.ui.Modal, title="Enter Challenger Names"):
    """Modal for entering challenger names via text input."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges):
        super().__init__()
        self.bot = bot
        self.cog = cog
        
        self.challenger1_input = discord.ui.TextInput(
            label="Challenger 1",
            placeholder="Type character name (partial matches work)...",
            required=True,
            max_length=100,
        )
        self.challenger2_input = discord.ui.TextInput(
            label="Challenger 2",
            placeholder="Type character name (partial matches work)...",
            required=True,
            max_length=100,
        )
        
        self.add_item(self.challenger1_input)
        self.add_item(self.challenger2_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        challenger1_input = self.challenger1_input.value.strip()
        challenger2_input = self.challenger2_input.value.strip()
        
        if not challenger1_input or not challenger2_input:
            await interaction.followup.send("❌ Both challenger names are required.", ephemeral=True)
            return
        
        # Find threads using fuzzy matching
        thread1 = await self.cog._find_character_thread(interaction.guild, challenger1_input)
        thread2 = await self.cog._find_character_thread(interaction.guild, challenger2_input)
        
        if not thread1:
            # Try to provide suggestions
            await self.cog._build_thread_cache(interaction.guild)
            cache = self.cog.thread_cache.get(interaction.guild.id, [])
            titles = [title for _, title, _ in cache]
            
            # Find closest matches
            from rapidfuzz import process
            matches = process.extract(challenger1_input, titles, limit=3)
            suggestions = "\n".join([f"- {match[0]}" for match in matches if match[1] >= 60])
            
            error_msg = f"❌ Could not find thread for **{challenger1_input}**."
            if suggestions:
                error_msg += f"\n\n**Did you mean one of these?**\n{suggestions}"
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        
        if not thread2:
            # Try to provide suggestions
            await self.cog._build_thread_cache(interaction.guild)
            cache = self.cog.thread_cache.get(interaction.guild.id, [])
            titles = [title for _, title, _ in cache]
            
            # Find closest matches
            from rapidfuzz import process
            matches = process.extract(challenger2_input, titles, limit=3)
            suggestions = "\n".join([f"- {match[0]}" for match in matches if match[1] >= 60])
            
            error_msg = f"❌ Could not find thread for **{challenger2_input}**."
            if suggestions:
                error_msg += f"\n\n**Did you mean one of these?**\n{suggestions}"
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        
        # Get the actual character names from the threads
        challenger1_name = thread1.name
        challenger2_name = thread2.name
        
        if challenger1_name.lower() == challenger2_name.lower():
            await interaction.followup.send("❌ Both challengers cannot be the same character.", ephemeral=True)
            return
        
        # Create view with winner selection buttons
        view = WinnerSelectionView(
            self.bot,
            self.cog,
            challenger1_name,
            challenger2_name,
            thread1,
            thread2,
            interaction.user
        )
        
        await interaction.followup.send(
            f"✅ Challenge recorded between **{challenger1_name}** and **{challenger2_name}**.\n\n"
            f"**Select the winner:**",
            view=view,
            ephemeral=True
        )


class WinnerButton(discord.ui.Button):
    """Button for selecting a winner."""
    
    def __init__(self, challenger_name: str, is_challenger1: bool, parent_view):
        self.challenger_name = challenger_name
        self.is_challenger1 = is_challenger1
        self.parent_view = parent_view
        super().__init__(
            label=f"{challenger_name} Wins",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )
    
    async def callback(self, interaction: Interaction):
        if self.is_challenger1:
            await self.parent_view._submit_for_approval(
                interaction,
                self.parent_view.challenger1,
                self.parent_view.challenger2,
                self.parent_view.thread1,
                self.parent_view.thread2
            )
        else:
            await self.parent_view._submit_for_approval(
                interaction,
                self.parent_view.challenger2,
                self.parent_view.challenger1,
                self.parent_view.thread2,
                self.parent_view.thread1
            )


class WinnerSelectionView(discord.ui.View):
    """View with buttons to select the winner."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, challenger1: str, challenger2: str, thread1: discord.Thread, thread2: discord.Thread, submitted_by: discord.Member):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.cog = cog
        self.challenger1 = challenger1
        self.challenger2 = challenger2
        self.thread1 = thread1
        self.thread2 = thread2
        self.submitted_by = submitted_by
        
        # Add buttons
        self.add_item(WinnerButton(challenger1, True, self))
        self.add_item(WinnerButton(challenger2, False, self))
    
    async def _submit_for_approval(self, interaction: Interaction, winner: str, loser: str, winner_thread: discord.Thread, loser_thread: discord.Thread):
        """Submit challenge result for admin approval."""
        await interaction.response.defer(ephemeral=True)
        
        # Send to approval channel
        approval_msg = await self.cog._send_approval_request(
            self.challenger1,
            self.challenger2,
            winner,
            loser,
            self.thread1,
            self.thread2,
            self.submitted_by
        )
        
        if not approval_msg:
            await interaction.followup.send(
                "❌ Failed to send approval request. Please contact an admin.",
                ephemeral=True
            )
            return
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.followup.send(
            f"✅ Challenge result submitted for approval!\n\n"
            f"**{winner}** defeated **{loser}**\n\n"
            f"An admin will review and approve before results are posted to character threads.",
            ephemeral=True
        )
        
        # Update the original message to show it's submitted
        try:
            await interaction.message.edit(
                content=f"✅ **Challenge Submitted for Approval**\n\n**{winner}** defeated **{loser}**\n\nAwaiting admin approval...",
                view=self
            )
        except Exception:
            pass


class AdjustRecordModal(discord.ui.Modal):
    """Modal for adjusting a character's challenge record."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, character_name: str, current_data: Dict):
        super().__init__(title=f"Adjust Record: {character_name[:40]}")  # Character name in title
        self.bot = bot
        self.cog = cog
        self.character_name = character_name
        self.current_data = current_data
        
        # Create text inputs with current values as placeholders
        # Note: Discord modals have a 5 input limit, so we show character name in title
        self.wins_input = discord.ui.TextInput(
            label="Total Wins",
            placeholder=f"Current: {current_data.get('wins', 0)}",
            default=str(current_data.get('wins', 0)),
            required=False,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.losses_input = discord.ui.TextInput(
            label="Total Losses",
            placeholder=f"Current: {current_data.get('losses', 0)}",
            default=str(current_data.get('losses', 0)),
            required=False,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.win_streak_input = discord.ui.TextInput(
            label="Current Win Streak",
            placeholder=f"Current: {current_data.get('current_win_streak', 0)}",
            default=str(current_data.get('current_win_streak', 0)),
            required=False,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.loss_streak_input = discord.ui.TextInput(
            label="Current Loss Streak",
            placeholder=f"Current: {current_data.get('current_loss_streak', 0)}",
            default=str(current_data.get('current_loss_streak', 0)),
            required=False,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.total_games_input = discord.ui.TextInput(
            label="Total Games",
            placeholder=f"Current: {current_data.get('total_games', 0)}",
            default=str(current_data.get('total_games', 0)),
            required=False,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.wins_input)
        self.add_item(self.losses_input)
        self.add_item(self.win_streak_input)
        self.add_item(self.loss_streak_input)
        self.add_item(self.total_games_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Parse input values (empty = keep current)
        def parse_int(value: str, current: int) -> Optional[int]:
            if not value or value.strip() == "":
                return None
            try:
                return max(0, int(value.strip()))
            except ValueError:
                return None
        
        old_values = {
            "wins": self.current_data.get("wins", 0),
            "losses": self.current_data.get("losses", 0),
            "current_win_streak": self.current_data.get("current_win_streak", 0),
            "current_loss_streak": self.current_data.get("current_loss_streak", 0),
            "total_games": self.current_data.get("total_games", 0)
        }
        
        # Load data
        data = self.cog._load_data()
        if self.character_name not in data:
            data[self.character_name] = {
                "wins": 0,
                "losses": 0,
                "current_win_streak": 0,
                "current_loss_streak": 0,
                "total_games": 0,
                "game_history": []
            }
        
        # Update values
        wins = parse_int(self.wins_input.value, old_values["wins"])
        losses = parse_int(self.losses_input.value, old_values["losses"])
        win_streak = parse_int(self.win_streak_input.value, old_values["current_win_streak"])
        loss_streak = parse_int(self.loss_streak_input.value, old_values["current_loss_streak"])
        total_games = parse_int(self.total_games_input.value, old_values["total_games"])
        
        if wins is not None:
            data[self.character_name]["wins"] = wins
        if losses is not None:
            data[self.character_name]["losses"] = losses
        if win_streak is not None:
            data[self.character_name]["current_win_streak"] = win_streak
        if loss_streak is not None:
            data[self.character_name]["current_loss_streak"] = loss_streak
        if total_games is not None:
            data[self.character_name]["total_games"] = total_games
        
        # Save changes
        self.cog._save_data(data)
        
        # Get new values
        new_values = data[self.character_name]
        
        # Build response showing changes
        changes = []
        if wins is not None and old_values["wins"] != new_values["wins"]:
            changes.append(f"**Wins:** {old_values['wins']} → {new_values['wins']}")
        if losses is not None and old_values["losses"] != new_values["losses"]:
            changes.append(f"**Losses:** {old_values['losses']} → {new_values['losses']}")
        if win_streak is not None and old_values["current_win_streak"] != new_values["current_win_streak"]:
            changes.append(f"**Win Streak:** {old_values['current_win_streak']} → {new_values['current_win_streak']}")
        if loss_streak is not None and old_values["current_loss_streak"] != new_values["current_loss_streak"]:
            changes.append(f"**Loss Streak:** {old_values['current_loss_streak']} → {new_values['current_loss_streak']}")
        if total_games is not None and old_values["total_games"] != new_values["total_games"]:
            changes.append(f"**Total Games:** {old_values['total_games']} → {new_values['total_games']}")
        
        if not changes:
            await interaction.followup.send(
                f"ℹ️ No changes made to **{self.character_name}**'s record.\n\n"
                f"**Current Stats:**\n"
                f"Wins: {old_values['wins']}\n"
                f"Losses: {old_values['losses']}\n"
                f"Win Streak: {old_values['current_win_streak']}\n"
                f"Loss Streak: {old_values['current_loss_streak']}\n"
                f"Total Games: {old_values['total_games']}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Updated **{self.character_name}**'s record:\n\n" + "\n".join(changes) + "\n\n"
                f"**Current Stats:**\n"
                f"Wins: {new_values['wins']}\n"
                f"Losses: {new_values['losses']}\n"
                f"Win Streak: {new_values['current_win_streak']}\n"
                f"Loss Streak: {new_values['current_loss_streak']}\n"
                f"Total Games: {new_values['total_games']}",
                ephemeral=True
            )


class ApprovalView(discord.ui.View):
    """View for admin approval of challenge results."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, challenger1: str, challenger2: str, winner: str, loser: str, thread1: discord.Thread, thread2: discord.Thread, submitted_by_id: int):
        super().__init__(timeout=None)  # Persistent buttons
        self.bot = bot
        self.cog = cog
        self.challenger1 = challenger1
        self.challenger2 = challenger2
        self.winner = winner
        self.loser = loser
        self.thread1 = thread1
        self.thread2 = thread2
        self.submitted_by_id = submitted_by_id
    
    async def interaction_check(self, interaction: Interaction) -> bool:
        """Check if user has admin permissions or is owner."""
        if not interaction.guild:
            return False
        
        # Check if user has administrator permission or is owner
        if not is_owner_or_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You need administrator permissions to approve challenges.",
                ephemeral=True
            )
            return False
        
        return True
    
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Record the result
        self.cog._record_result(self.winner, self.loser)
        
        # Get updated streaks
        winner_streaks = self.cog._get_streaks(self.winner)
        loser_streaks = self.cog._get_streaks(self.loser)
        
        # Post to both threads
        await self.cog._post_to_character_thread(self.thread1, self.winner, winner_streaks)
        await self.cog._post_to_character_thread(self.thread2, self.loser, loser_streaks)
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        # Update embed
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.color = discord.Color.green()
            embed.title = "🎲 Dice Challenge - Approved ✅"
            embed.add_field(name="Approved by", value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=False)
        
        await interaction.message.edit(embed=embed, view=self)
        
        await interaction.followup.send(
            f"✅ Challenge approved! Results posted to character threads.",
            ephemeral=True
        )
        
        # Notify the submitter if possible
        try:
            guild = interaction.guild
            if guild:
                submitter = guild.get_member(self.submitted_by_id)
                if submitter:
                    try:
                        await submitter.send(
                            f"✅ Your dice challenge result has been approved!\n\n"
                            f"**{self.winner}** defeated **{self.loser}**\n\n"
                            f"Results have been posted to both character threads."
                        )
                    except discord.Forbidden:
                        pass  # User has DMs disabled
        except Exception as e:
            print(f"[DiceChallenges] Failed to notify submitter: {e}")
    
    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        # Update embed
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.color = discord.Color.red()
            embed.title = "🎲 Dice Challenge - Rejected ❌"
            embed.add_field(name="Rejected by", value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=False)
        
        await interaction.message.edit(embed=embed, view=self)
        
        await interaction.followup.send(
            f"❌ Challenge rejected.",
            ephemeral=True
        )
        
        # Notify the submitter if possible
        try:
            guild = interaction.guild
            if guild:
                submitter = guild.get_member(self.submitted_by_id)
                if submitter:
                    try:
                        await submitter.send(
                            f"❌ Your dice challenge result has been rejected.\n\n"
                            f"**{self.winner}** vs **{self.loser}**\n\n"
                            f"Please verify the results and resubmit if needed."
                        )
                    except discord.Forbidden:
                        pass  # User has DMs disabled
        except Exception as e:
            print(f"[DiceChallenges] Failed to notify submitter: {e}")


class MessageConfigModal(discord.ui.Modal, title="Configure Message Header"):
    """Modal for configuring the message header."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, parent_view):
        super().__init__()
        self.bot = bot
        self.cog = cog
        self.parent_view = parent_view
        
        self.header_input = discord.ui.TextInput(
            label="Message Header",
            placeholder="e.g., ## 🎲 Dice Challenge Results",
            default=self.parent_view.current_header,
            required=True,
            max_length=200,
        )
        self.add_item(self.header_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        new_header = self.header_input.value.strip()
        self.parent_view.current_header = new_header
        
        await interaction.followup.send(
            f"✅ Header updated to: **{new_header}**\n\n"
            f"Use the buttons below to select which fields to display, then click 'Save Configuration'.",
            ephemeral=True
        )


class FieldToggleButton(discord.ui.Button):
    """Button that toggles a field on/off."""
    
    def __init__(self, field_key: str, field_label: str, is_selected: bool, parent_view):
        self.field_key = field_key
        self.parent_view = parent_view
        self.is_selected = is_selected
        
        # Truncate label if too long and add checkmark if selected
        display_label = field_label
        if len(display_label) > 75:
            display_label = display_label[:72] + "..."
        if is_selected:
            display_label = "✓ " + display_label
        
        # Determine row (max 5 buttons per row, we have 5 fields so all on row 0)
        existing_field_buttons = len([c for c in parent_view.children if isinstance(c, FieldToggleButton)])
        row = 0 if existing_field_buttons < 5 else 1
        
        super().__init__(
            label=display_label,
            style=discord.ButtonStyle.success if is_selected else discord.ButtonStyle.secondary,
            row=row
        )
    
    async def callback(self, interaction: Interaction):
        # Toggle selection
        if self.field_key in self.parent_view.selected_fields:
            self.parent_view.selected_fields.remove(self.field_key)
            self.is_selected = False
        else:
            self.parent_view.selected_fields.add(self.field_key)
            self.is_selected = True
        
        # Update button style and label
        display_label = self.parent_view.field_options[self.field_key]
        if len(display_label) > 75:
            display_label = display_label[:72] + "..."
        if self.is_selected:
            display_label = "✓ " + display_label
        
        self.label = display_label
        self.style = discord.ButtonStyle.success if self.is_selected else discord.ButtonStyle.secondary
        
        # Update the message with the new view state (this is the response)
        await interaction.response.edit_message(view=self.parent_view)


class EditHeaderButton(discord.ui.Button):
    """Button to edit the header."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, parent_view):
        super().__init__(label="Edit Header", style=discord.ButtonStyle.primary, row=2)
        self.bot = bot
        self.cog = cog
        self.parent_view = parent_view
    
    async def callback(self, interaction: Interaction):
        modal = MessageConfigModal(self.bot, self.cog, self.parent_view)
        await interaction.response.send_modal(modal)


class SaveConfigButton(discord.ui.Button):
    """Button to save the configuration."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, parent_view):
        super().__init__(label="Save Configuration", style=discord.ButtonStyle.success, row=2)
        self.bot = bot
        self.cog = cog
        self.parent_view = parent_view
    
    async def callback(self, interaction: Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not self.parent_view.selected_fields:
            await interaction.response.send_message("❌ You must select at least one field to display.", ephemeral=True)
            return
        
        # Save configuration
        self.cog.set_guild_config(
            interaction.guild.id,
            message_header=self.parent_view.current_header,
            message_fields=list(self.parent_view.selected_fields)
        )
        
        # Disable all buttons
        for item in self.parent_view.children:
            item.disabled = True
        
        field_names = [self.parent_view.field_options.get(f, f) for f in self.parent_view.selected_fields]
        
        # Edit the message with disabled buttons and success message
        success_text = (
            f"✅ **Message format configured!**\n\n"
            f"**Header:** {self.parent_view.current_header}\n"
            f"**Fields:** {', '.join(field_names)}"
        )
        
        try:
            await interaction.response.edit_message(content=success_text, view=self.parent_view)
        except Exception as e:
            # Fallback if edit fails
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(success_text, ephemeral=True)


class MessageConfigView(discord.ui.View):
    """View for configuring message format with field toggle buttons."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges, current_header: str, current_fields: List[str]):
        super().__init__(timeout=300)
        self.bot = bot
        self.cog = cog
        self.current_header = current_header
        self.selected_fields = set(current_fields)
        
        # Available fields
        self.field_options = {
            "current_streak": "Current Streak (Win/Loss)",
            "total_wins": "Total Wins",
            "total_losses": "Total Losses",
            "total_games": "Total Games",
            "streak_warning": "Streak Warning (3+ losses)"
        }
        
        # Create toggle buttons for each field
        for field_key, field_label in self.field_options.items():
            self.add_item(FieldToggleButton(
                field_key,
                field_label,
                field_key in self.selected_fields,
                self
            ))
        
        # Add control buttons on row 2
        self.add_item(EditHeaderButton(self.bot, self.cog, self))
        self.add_item(SaveConfigButton(self.bot, self.cog, self))
    
    async def _update_view(self, interaction: Interaction):
        """Update the view after field toggles."""
        # This method is no longer needed since we edit in the callback
        pass


class FinishChallengeView(discord.ui.View):
    """View with the "Finish Challenge" button."""
    
    def __init__(self, bot: commands.Bot, cog: DiceChallenges):
        super().__init__(timeout=None)  # Persistent button
        self.bot = bot
        self.cog = cog
    
    @discord.ui.button(label="Finish Challenge", style=discord.ButtonStyle.primary, emoji="🏁", custom_id="finish_challenge_btn")
    async def finish_challenge(self, interaction: Interaction, button: discord.ui.Button):
        # Check guild
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        # Check if button channel is configured for this guild
        guild_config = self.cog.get_guild_config(interaction.guild.id)
        if not guild_config.get("button_channel_id"):
            await interaction.response.send_message("❌ Challenge system not configured for this server. An admin needs to set up channels.", ephemeral=True)
            return
        
        # Show modal with text inputs
        modal = ChallengerInputModal(self.bot, self.cog)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    cog = DiceChallenges(bot)
    await bot.add_cog(cog)
    
    # Remove existing command/group if it exists (for reloads)
    try:
        bot.tree.remove_command("challenge")
        print("[DiceChallenges] Removed existing challenge command")
    except Exception as e:
        print(f"[DiceChallenges] No existing challenge command to remove: {e}")
    
    # Add the command group
    try:
        bot.tree.add_command(cog.challenge_group)
        print("[DiceChallenges] Successfully added challenge command group")
    except Exception as e:
        print(f"[DiceChallenges] ERROR: Failed to add challenge command group: {e}")
        import traceback
        traceback.print_exc()
    
    print("[DiceChallenges] Successfully loaded dice challenges cog")
