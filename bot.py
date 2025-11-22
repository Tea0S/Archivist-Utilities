# bot.py
import logging, discord, asyncio
import os
from pathlib import Path
from discord.ext import commands
from discord import app_commands
from cogwatch import Watcher
from core.config import settings
from core.utils import is_owner

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("bot")

# Configure cogwatch logger to show reload/load activity
watch_log = logging.getLogger("cogwatch")
watch_log.setLevel(logging.INFO)
watch_log.propagate = True  # Use the root logger's handlers

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.guilds = True
intents.guild_messages = True
intents.guild_reactions = True

bot = commands.AutoShardedBot(command_prefix="!", intents=intents)


COGS = [

    "cogs.quests",
    #"cogs.healthcheck",
    "cogs.characters",
    "cogs.index_manager",
    "cogs.edit_reaction",
    "cogs.post_as_bot",
    "cogs.resync",
    "cogs.move",
    "cogs.move_any",
    "cogs.move_thread",
    "cogs.dice_challenges",
    "cogs.lore_carousel",
    "cogs.bot_customization"
]

# Built-in ping command to test Google Sheets API connection
# Commented out - not using Google API for this one
# @bot.tree.command(name="ping", description="Test the bot's Google Sheets API connection")
# async def ping(interaction: discord.Interaction):
#     await interaction.response.defer(ephemeral=True, thinking=True)
#     import json
#     import asyncio
#     from core.sheets_service import ping as sheets_ping
#     
#     # Run the blocking function in an executor
#     loop = asyncio.get_event_loop()
#     data = await loop.run_in_executor(None, sheets_ping)
#     
#     raw = json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)
#     if len(raw) > 1800: 
#         raw = raw[:1800] + "... [truncated]"
#     ok = isinstance(data, dict) and data.get("ok", False)
#     await interaction.followup.send(
#         f"Google Sheets API ping → ok={ok}\n```json\n{raw}\n```", 
#         ephemeral=True
#     )

async def sync_commands():
    """Helper to sync slash commands."""
    if settings.GUILD_ID:
        guild = discord.Object(id=settings.GUILD_ID)
        synced_guild = await bot.tree.sync(guild=guild)
        log.info("Guild-synced %d commands to %s", len(synced_guild), settings.GUILD_ID)
        for c in synced_guild:
            log.info(" - /%s (guild)", c.name)
        
        # Also sync global commands (for commands that work across multiple guilds)
        synced_global = await bot.tree.sync()
        if synced_global:
            log.info("Globally synced %d commands", len(synced_global))
            for c in synced_global:
                log.info(" - /%s (global)", c.name)
    else:
        synced = await bot.tree.sync()
        log.info("Globally synced %d commands", len(synced))
        for c in synced:
            log.info(" - /%s", c.name)

@bot.event
async def setup_hook():
    # Initial cog loading - cogwatch will handle auto-reloading on file changes
    # We keep manual loading here for explicit control and error handling
    for ext in COGS:
        try:
            await bot.load_extension(ext)
            log.info("Loaded cog: %s", ext)
        except Exception as e:
            log.exception("Failed to load %s: %s", ext, e)

    # Sync commands after initial load
    await sync_commands()

async def polling_file_watcher(bot, cogs_dir: Path, interval: float = 2.0):
    """
    Polling-based file watcher that works reliably in Docker containers.
    Checks file modification times periodically and reloads changed cogs.
    """
    # Map of cog file paths to their last modification time
    file_mtimes = {}
    
    # Initialize file modification times
    for cog_file in cogs_dir.glob("*.py"):
        if cog_file.name != "__init__.py":
            try:
                file_mtimes[str(cog_file)] = cog_file.stat().st_mtime
            except OSError:
                pass
    
    log.info("🔍 Polling file watcher started (checking every %.1fs)", interval)
    
    while True:
        try:
            await asyncio.sleep(interval)
            
            # Check each cog file for changes
            for cog_file in cogs_dir.glob("*.py"):
                if cog_file.name == "__init__.py":
                    continue
                
                cog_path = str(cog_file)
                cog_name = cog_file.stem
                extension_name = f"cogs.{cog_name}"
                
                try:
                    current_mtime = cog_file.stat().st_mtime
                    last_mtime = file_mtimes.get(cog_path)
                    
                    # File was modified or is new
                    if last_mtime is None or current_mtime > last_mtime:
                        file_mtimes[cog_path] = current_mtime
                        
                        # Skip if this is the initial scan
                        if last_mtime is None:
                            continue
                        
                        log.info("📝 Detected change in %s", cog_file.name)
                        
                        # Reload the extension
                        try:
                            if extension_name in bot.extensions:
                                await bot.reload_extension(extension_name)
                                log.info("✅ Reloaded cog: %s", extension_name)
                            else:
                                await bot.load_extension(extension_name)
                                log.info("✅ Loaded new cog: %s", extension_name)
                            
                            # Sync commands after reload
                            await sync_commands()
                        except commands.ExtensionNotLoaded:
                            # Extension was unloaded, try to load it
                            try:
                                await bot.load_extension(extension_name)
                                log.info("✅ Loaded cog: %s", extension_name)
                                await sync_commands()
                            except Exception as e:
                                log.error("❌ Failed to load %s: %s", extension_name, e)
                        except Exception as e:
                            log.error("❌ Failed to reload %s: %s", extension_name, e)
                
                except OSError as e:
                    # File might have been deleted
                    if cog_path in file_mtimes:
                        del file_mtimes[cog_path]
                        log.info("🗑️  File removed: %s", cog_file.name)
        
        except Exception as e:
            log.error("❌ Error in polling file watcher: %s", e, exc_info=True)

@bot.check
async def owner_bypass_check(ctx: commands.Context) -> bool:
    """
    Global check that allows the owner to bypass all permission checks.
    This works for prefix commands. For slash commands, see individual handlers.
    """
    if ctx.author and is_owner(ctx.author):
        log.debug(f"Owner {ctx.author} ({ctx.author.id}) bypassing permission check for command: {ctx.command}")
        return True
    return True  # Let other checks handle permissions

@bot.tree.interaction_check
async def owner_bypass_interaction_check(interaction: discord.Interaction) -> bool:
    """
    Global check for slash commands that allows owner to bypass permission checks.
    Note: @app_commands.default_permissions is checked by Discord before this runs,
    so manual checks in command handlers are still needed.
    """
    if is_owner(interaction.user):
        log.debug(f"Owner {interaction.user} ({interaction.user.id}) attempting command: {interaction.command.name if interaction.command else 'unknown'}")
        # Return True to allow the command to proceed
        # Individual command handlers should also check is_owner_or_admin()
        return True
    return True  # Let other checks handle permissions normally

@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    
    # Initialize file watcher
    # NOTE: cogwatch uses file system events which don't work reliably in Docker
    # We use a polling-based watcher instead when ENABLE_COGWATCH is true
    if settings.ENABLE_COGWATCH:
        cogs_path = Path(__file__).parent / 'cogs'
        
        # Try cogwatch first (works better on native systems)
        # Fall back to polling watcher if cogwatch fails or in Docker
        use_polling = os.getenv("USE_POLLING_WATCHER", "false").lower() in ("true", "1", "yes")
        
        if not use_polling:
            try:
                log.info("Initializing cogwatch watcher for path: %s", cogs_path)
                bot.watcher = Watcher(bot, path='cogs', preload=False, debug=True, default_logger=True)
                await bot.watcher.start()
                log.info("🔍 Cogwatch is watching 'cogs/' directory for file changes")
            except Exception as e:
                log.warning("⚠️  Cogwatch failed, falling back to polling watcher: %s", e)
                use_polling = True
        
        if use_polling:
            # Start polling-based file watcher (works reliably in Docker)
            poll_interval = float(os.getenv("COGWATCH_POLL_INTERVAL", "2.0"))
            bot.loop.create_task(polling_file_watcher(bot, cogs_path, poll_interval))
    else:
        log.info("⏭️  File watching is disabled (set ENABLE_COGWATCH=true to enable)")
    
    # Sync commands on ready
    await sync_commands()

# Add event listeners to log when cogs are reloaded by cogwatch
@bot.event
async def on_extension_load(extension_name: str):
    """Called when an extension is loaded."""
    log.info("📦 Extension loaded: %s", extension_name)

@bot.event
async def on_extension_reload(extension_name: str):
    """Called when an extension is reloaded."""
    log.info("🔄 Extension reloaded: %s (cogwatch detected file change)", extension_name)
    # Auto-sync commands after reload
    try:
        await sync_commands()
        log.info("✅ Commands synced after reload of %s", extension_name)
    except Exception as e:
        log.error("❌ Failed to sync commands after reload: %s", e)

@bot.event
async def on_extension_unload(extension_name: str):
    """Called when an extension is unloaded."""
    log.info("📤 Extension unloaded: %s", extension_name)

bot.run(settings.DISCORD_TOKEN)
