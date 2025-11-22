# cogs/lore_carousel.py

import json
import os
import asyncio
import re
from typing import Optional, Dict, List, Union
import discord
from discord.ext import commands
from discord import app_commands, Interaction

# Data file path
CAROUSELS_DATA_FILE = "data/lore_carousels.json"
SELECTORS_DATA_FILE = "data/lore_carousels.json"  # Same file, different section


def get_channel_or_thread(guild: discord.Guild, channel_id: int) -> Optional[discord.abc.Messageable]:
    """
    Get a channel or thread by ID. Works for both regular channels and threads.
    Returns None if not found.
    """
    if not guild:
        return None
    
    # First try to get as a regular channel
    channel = guild.get_channel(channel_id)
    if channel:
        return channel
    
    # If not found, try to get as a thread
    thread = guild.get_thread(channel_id)
    if thread:
        return thread
    
    # If still not found, try searching through all channels for threads
    # This handles cases where threads might not be in the cache
    for channel in guild.channels:
        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            # Check active threads
            for thread in channel.threads:
                if thread.id == channel_id:
                    return thread
    
    return None


class LoreCarouselConfig:
    """Manages lore carousel data stored in JSON."""
    
    def __init__(self, data_file: str = CAROUSELS_DATA_FILE):
        self.data_file = data_file
        self._ensure_data_file()
    
    def _ensure_data_file(self):
        """Ensure the data file and directory exist."""
        dir_path = os.path.dirname(self.data_file)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        if not os.path.exists(self.data_file):
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump({"carousels": {}, "selectors": {}}, f, indent=2)
        else:
            # Ensure selectors section exists
            data = self._load()
            if "selectors" not in data:
                data["selectors"] = {}
                self._save(data)
    
    def _load(self) -> dict:
        """Load data from file."""
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "carousels" not in data:
                    data["carousels"] = {}
                if "selectors" not in data:
                    data["selectors"] = {}
                return data
        except Exception:
            return {"carousels": {}, "selectors": {}}
    
    def _save(self, data: dict):
        """Save data to file."""
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def get_carousel_key(self, message_id: int) -> str:
        """Get the key for a carousel."""
        return str(message_id)
    
    def add_carousel(self, channel_id: int, pages: List[Dict] = None, message_id: Optional[int] = None, ephemeral_mode: bool = False, guild_id: Optional[int] = None, original_message_id: Optional[int] = None):
        """Add or update a carousel. If original_message_id is provided, this is a repost and pages will be referenced from the original."""
        if not message_id:
            raise ValueError("message_id is required")
        
        data = self._load()
        key = self.get_carousel_key(message_id)
        # Preserve existing ephemeral_mode and ephemeral_text if updating
        existing = data["carousels"].get(key, {})
        carousel_data = {
            "channel_id": channel_id,
            "message_id": message_id,
            "pages": pages if pages is not None else (existing.get("pages", []) if not original_message_id else []),
            "ephemeral_mode": ephemeral_mode if key not in data["carousels"] else existing.get("ephemeral_mode", False),
            "ephemeral_title": existing.get("ephemeral_title", "📚 Lore Carousel"),
            "ephemeral_description": existing.get("ephemeral_description", "Click the button below to start exploring!"),
            "ephemeral_button_label": existing.get("ephemeral_button_label", "Start Here"),
            "ephemeral_image_url": existing.get("ephemeral_image_url")  # Preserve existing image
        }
        # Add guild_id if provided, otherwise preserve existing or try to infer from channel
        if guild_id:
            carousel_data["guild_id"] = guild_id
        elif "guild_id" in existing:
            carousel_data["guild_id"] = existing["guild_id"]
        # Store original_message_id if this is a repost
        if original_message_id:
            carousel_data["original_message_id"] = original_message_id
        data["carousels"][key] = carousel_data
        self._save(data)
    
    def set_ephemeral_mode(self, message_id: int, ephemeral_mode: bool):
        """Set the ephemeral mode for a carousel."""
        carousel = self.get_carousel(message_id)
        if not carousel:
            raise ValueError(f"Carousel with message_id {message_id} not found")
        
        data = self._load()
        key = self.get_carousel_key(message_id)
        if key in data["carousels"]:
            data["carousels"][key]["ephemeral_mode"] = ephemeral_mode
            self._save(data)
    
    def set_ephemeral_text(self, message_id: int, title: str, description: str, button_label: str, image_url: Optional[str] = None):
        """Set the custom text for ephemeral mode."""
        carousel = self.get_carousel(message_id)
        if not carousel:
            raise ValueError(f"Carousel with message_id {message_id} not found")
        
        data = self._load()
        key = self.get_carousel_key(message_id)
        if key in data["carousels"]:
            data["carousels"][key]["ephemeral_title"] = title
            data["carousels"][key]["ephemeral_description"] = description
            data["carousels"][key]["ephemeral_button_label"] = button_label
            if image_url is not None:
                data["carousels"][key]["ephemeral_image_url"] = image_url
            self._save(data)
    
    def get_carousel(self, message_id: int, _resolving_repost: bool = False) -> Optional[Dict]:
        """Get a carousel by message ID. If it's a repost, resolve the original carousel's pages.
        
        Args:
            message_id: The message ID of the carousel to get
            _resolving_repost: Internal flag to prevent infinite recursion when resolving reposts
        """
        data = self._load()
        # First try the key (for backward compatibility)
        key = self.get_carousel_key(message_id)
        carousel = data["carousels"].get(key)
        if not carousel:
            # If not found by key, search by message_id in the data
            # (handles cases where key doesn't match message_id)
            for carousel_data in data["carousels"].values():
                if carousel_data.get("message_id") == message_id:
                    carousel = carousel_data
                    break
        
        if not carousel:
            return None
        
        # If this is a repost (has original_message_id), resolve the pages from the original
        # Only resolve if we're not already resolving (to prevent infinite loops)
        original_message_id = carousel.get("original_message_id")
        if original_message_id and not carousel.get("pages") and not _resolving_repost:
            # This is a repost - get pages from the original carousel
            # Pass _resolving_repost=True to prevent infinite recursion
            original_carousel = self.get_carousel(original_message_id, _resolving_repost=True)
            if original_carousel and original_carousel.get("pages"):
                # Create a copy with the original pages but keep repost-specific data
                resolved_carousel = carousel.copy()
                resolved_carousel["pages"] = original_carousel["pages"]
                return resolved_carousel
            
            # If original doesn't exist or has no pages, try to find another repost
            # of the same original that has pages stored directly (fallback)
            if not original_carousel or not original_carousel.get("pages"):
                data = self._load()
                for other_carousel_data in data["carousels"].values():
                    # Look for another repost of the same original that has pages
                    if (other_carousel_data.get("original_message_id") == original_message_id and
                        other_carousel_data.get("pages") and
                        other_carousel_data.get("message_id") != message_id):
                        # Found another repost with pages - use those
                        resolved_carousel = carousel.copy()
                        resolved_carousel["pages"] = other_carousel_data["pages"]
                        return resolved_carousel
            
            # If we can't find pages anywhere, return the repost as-is
            # (it should have pages stored directly if original was missing when reposted)
        
        return carousel
    
    def get_ephemeral_carousels_by_guild(self, guild_id: int, bot=None) -> List[Dict]:
        """Get all ephemeral carousels for a guild."""
        return self.get_carousels_by_guild(guild_id, bot, ephemeral_only=True)
    
    def get_carousels_by_guild(self, guild_id: int, bot=None, ephemeral_only: bool = False) -> List[Dict]:
        """Get all carousels for a guild (optionally filter to ephemeral only)."""
        data = self._load()
        carousels = []
        for carousel_data in data.get("carousels", {}).values():
            # Filter by ephemeral mode if requested
            if ephemeral_only and not carousel_data.get("ephemeral_mode", False):
                continue
            if not carousel_data.get("pages"):
                continue
            
            carousel_guild_id = carousel_data.get("guild_id")
            channel_id = carousel_data.get("channel_id")
            
            # Check if guild_id matches
            if carousel_guild_id == guild_id:
                carousels.append(carousel_data)
            elif carousel_guild_id is None and bot and channel_id:
                # Fallback: check if channel belongs to this guild (for unmigrated carousels)
                try:
                    guild = bot.get_guild(guild_id)
                    if guild and get_channel_or_thread(guild, channel_id):
                        carousels.append(carousel_data)
                except:
                    pass
        
        return carousels
    
    def migrate_add_guild_ids(self, bot):
        """Retroactively add guild_id to carousels that don't have it."""
        data = self._load()
        updated = False
        
        for key, carousel in data.get("carousels", {}).items():
            if "guild_id" not in carousel:
                channel_id = carousel.get("channel_id")
                if channel_id:
                    # Try to find the guild from the channel
                    for guild in bot.guilds:
                        channel = get_channel_or_thread(guild, channel_id)
                        if channel:
                            carousel["guild_id"] = guild.id
                            updated = True
                            break
        
        # Also migrate selectors
        for key, selector in data.get("selectors", {}).items():
            if "guild_id" not in selector:
                channel_id = selector.get("channel_id")
                if channel_id:
                    for guild in bot.guilds:
                        channel = get_channel_or_thread(guild, channel_id)
                        if channel:
                            selector["guild_id"] = guild.id
                            updated = True
                            break
        
        if updated:
            self._save(data)
    
    def get_carousel_by_channel(self, channel_id: int) -> Optional[Dict]:
        """Get the most recent carousel in a channel (for backward compatibility)."""
        data = self._load()
        carousels = data.get("carousels", {})
        # Find carousel in this channel - the key is the message_id
        for key, carousel_data in carousels.items():
            if carousel_data.get("channel_id") == channel_id:
                # Ensure message_id is set from the key
                try:
                    message_id = int(key)
                    carousel_data["message_id"] = message_id
                except ValueError:
                    pass
                return carousel_data
        return None
    
    def add_page(self, message_id: int, header: str, body: str, image_url: Optional[str] = None):
        """Add a page to a carousel."""
        carousel = self.get_carousel(message_id)
        if not carousel:
            raise ValueError(f"Carousel with message_id {message_id} not found")
        
        page = {
            "header": header,
            "body": body,
            "image_url": image_url
        }
        carousel["pages"].append(page)
        self.add_carousel(carousel["channel_id"], carousel["pages"], message_id)
        return len(carousel["pages"]) - 1  # Return page index
    
    def update_page(self, message_id: int, page_index: int, header: str, body: str, image_url: Optional[str] = None):
        """Update a page in a carousel."""
        carousel = self.get_carousel(message_id)
        if not carousel or page_index >= len(carousel["pages"]):
            return False
        
        carousel["pages"][page_index] = {
            "header": header,
            "body": body,
            "image_url": image_url
        }
        self.add_carousel(carousel["channel_id"], carousel["pages"], message_id)
        return True
    
    def remove_page(self, message_id: int, page_index: int):
        """Remove a page from a carousel."""
        carousel = self.get_carousel(message_id)
        if not carousel or page_index >= len(carousel["pages"]):
            return False
        
        carousel["pages"].pop(page_index)
        self.add_carousel(carousel["channel_id"], carousel["pages"], message_id)
        return True
    
    def remove_carousel(self, message_id: int):
        """Remove a carousel."""
        data = self._load()
        key = self.get_carousel_key(message_id)
        data["carousels"].pop(key, None)
        self._save(data)
    
    # Selector methods
    def add_selector(self, channel_id: int, message_id: int, title: str = "📚 Lore Carousels", description: str = "Select a carousel to explore:", guild_id: Optional[int] = None, image_url: Optional[str] = None):
        """Add or update a carousel selector."""
        data = self._load()
        key = self.get_carousel_key(message_id)
        existing = data["selectors"].get(key, {})
        selector_data = {
            "channel_id": channel_id,
            "message_id": message_id,
            "title": title,
            "description": description,
            "carousels": existing.get("carousels", []),  # Preserve existing carousels
            "links": existing.get("links", []),  # Preserve existing links
            "image_url": image_url if image_url else existing.get("image_url")  # Preserve existing image if not provided
        }
        if guild_id:
            selector_data["guild_id"] = guild_id
        elif "guild_id" in existing:
            selector_data["guild_id"] = existing["guild_id"]
        data["selectors"][key] = selector_data
        self._save(data)
    
    def get_selector(self, message_id: int) -> Optional[Dict]:
        """Get a selector by message ID."""
        data = self._load()
        key = self.get_carousel_key(message_id)
        selector = data["selectors"].get(key)
        if selector:
            return selector
        
        # Search by message_id in the data
        for selector_data in data["selectors"].values():
            if selector_data.get("message_id") == message_id:
                return selector_data
        
        return None
    
    def add_carousel_to_selector(self, selector_message_id: int, carousel_message_id: int, button_label: str):
        """Add a carousel to a selector."""
        selector = self.get_selector(selector_message_id)
        if not selector:
            raise ValueError(f"Selector with message_id {selector_message_id} not found")
        
        # Check if carousel already exists
        carousels = selector.get("carousels", [])
        for item in carousels:
            if item.get("message_id") == carousel_message_id:
                # Update label
                item["button_label"] = button_label
                break
        else:
            # Check limit: 24 carousel buttons + 1 admin button = 25 total (Discord's max)
            if len(carousels) >= 24:
                raise ValueError("Selector is full! Maximum 24 carousels allowed (plus 1 admin button = 25 total buttons, Discord's limit).")
            
            # Add new carousel
            carousels.append({
                "message_id": carousel_message_id,
                "button_label": button_label
            })
        
        # Save
        data = self._load()
        key = self.get_carousel_key(selector_message_id)
        data["selectors"][key]["carousels"] = carousels
        self._save(data)
    
    def remove_carousel_from_selector(self, selector_message_id: int, carousel_message_id: int):
        """Remove a carousel from a selector."""
        selector = self.get_selector(selector_message_id)
        if not selector:
            raise ValueError(f"Selector with message_id {selector_message_id} not found")
        
        carousels = selector.get("carousels", [])
        carousels = [item for item in carousels if item.get("message_id") != carousel_message_id]
        
        data = self._load()
        key = self.get_carousel_key(selector_message_id)
        data["selectors"][key]["carousels"] = carousels
        self._save(data)
    
    def add_link_to_selector(self, selector_message_id: int, channel_id: int, button_label: str):
        """Add a link button to a selector."""
        selector = self.get_selector(selector_message_id)
        if not selector:
            raise ValueError(f"Selector with message_id {selector_message_id} not found")
        
        # Get current links and carousels to check total button count
        links = selector.get("links", [])
        carousels = selector.get("carousels", [])
        
        # Check limit: 24 total buttons (carousels + links) + 1 admin button = 25 total (Discord's max)
        total_buttons = len(carousels) + len(links)
        if total_buttons >= 24:
            raise ValueError("Selector is full! Maximum 24 buttons allowed (plus 1 admin button = 25 total buttons, Discord's limit).")
        
        # Check if link already exists for this channel
        for item in links:
            if item.get("channel_id") == channel_id:
                # Update label
                item["button_label"] = button_label
                break
        else:
            # Add new link
            links.append({
                "channel_id": channel_id,
                "button_label": button_label
            })
        
        # Save
        data = self._load()
        key = self.get_carousel_key(selector_message_id)
        data["selectors"][key]["links"] = links
        self._save(data)
    
    def remove_link_from_selector(self, selector_message_id: int, channel_id: int):
        """Remove a link button from a selector."""
        selector = self.get_selector(selector_message_id)
        if not selector:
            raise ValueError(f"Selector with message_id {selector_message_id} not found")
        
        links = selector.get("links", [])
        links = [item for item in links if item.get("channel_id") != channel_id]
        
        data = self._load()
        key = self.get_carousel_key(selector_message_id)
        data["selectors"][key]["links"] = links
        self._save(data)
    
    def remove_selector(self, message_id: int):
        """Remove a selector."""
        data = self._load()
        key = self.get_carousel_key(message_id)
        if key in data["selectors"]:
            data["selectors"].pop(key)
            self._save(data)


class EphemeralAdminView(discord.ui.View):
    """Admin view for ephemeral carousels."""
    
    def __init__(self, cog, message_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
    
    @discord.ui.button(label="➕ Add Page", style=discord.ButtonStyle.success, row=0)
    async def add_page(self, interaction: Interaction, button: discord.ui.Button):
        """Handle add page button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to add pages.", ephemeral=True)
            return
        
        modal = AddPageModal(self.cog, self.message_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✏️ Edit Page", style=discord.ButtonStyle.primary, row=0)
    async def edit_page(self, interaction: Interaction, button: discord.ui.Button):
        """Handle edit page button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to edit pages.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available to edit.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        if len(pages) == 1:
            # If only one page, edit it directly
            edit_modal = EditPageModal(self.cog, self.message_id, 0, pages[0])
            await interaction.response.send_modal(edit_modal)
        else:
            # Show select menu to choose which page to edit
            select_view = SelectPageView(self.cog, self.message_id, pages)
            await interaction.response.send_message("Select a page to edit:", view=select_view, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Remove Page", style=discord.ButtonStyle.danger, row=0)
    async def remove_page(self, interaction: Interaction, button: discord.ui.Button):
        """Handle remove page button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to remove pages.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available to remove.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        if len(pages) == 1:
            await interaction.response.send_message("❌ Cannot remove the last page. Delete the carousel instead with `/lore remove`.", ephemeral=True)
            return
        
        # Show select menu to choose which page to remove
        remove_view = RemovePageView(self.cog, self.message_id, pages)
        await interaction.response.send_message("Select a page to remove:", view=remove_view, ephemeral=True)
    
    @discord.ui.button(label="✏️ Edit Text", style=discord.ButtonStyle.secondary, row=1)
    async def edit_text(self, interaction: Interaction, button: discord.ui.Button):
        """Edit the ephemeral carousel text."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        modal = EphemeralConfigModal(self.cog, self.message_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: Interaction, button: discord.ui.Button):
        """Handle refresh button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to refresh the carousel.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No carousel found.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Refresh the ephemeral carousel message
        channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
        if channel:
            await interaction.followup.send("✅ Carousel data refreshed! The 'Start Here' button will show the latest pages.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
    
    @discord.ui.button(label="🔀 Switch to Standard", style=discord.ButtonStyle.primary, row=1)
    async def switch_to_standard(self, interaction: Interaction, button: discord.ui.Button):
        """Switch carousel back to standard mode."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Set mode to standard
        self.cog.config.set_ephemeral_mode(self.message_id, False)
        
        # Update the message
        carousel = self.cog.config.get_carousel(self.message_id)
        if carousel:
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                try:
                    await self.cog.update_carousel_message(channel, message_id=self.message_id)
                    await interaction.followup.send("✅ Carousel converted to standard mode! The full carousel is now visible in the channel.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"❌ Error updating carousel: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("❌ Channel not found.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Carousel not found.", ephemeral=True)


class CarouselSelectorView(discord.ui.View):
    """View with buttons for multiple ephemeral carousels."""
    
    def __init__(self, cog, selector_message_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.selector_message_id = selector_message_id
        
        # Load selector data
        selector = cog.config.get_selector(selector_message_id)
        if not selector:
            return
        
        # Create buttons for each carousel and link (max 5 buttons per row, max 5 rows = 25 buttons total)
        # Limit: 24 total buttons (carousels + links) + 1 admin button = 25 total (Discord's max)
        carousels = selector.get("carousels", [])
        links = selector.get("links", [])
        
        # Combine carousels and links, but track which is which
        all_items = []
        for carousel_item in carousels:
            all_items.append(("carousel", carousel_item))
        for link_item in links:
            all_items.append(("link", link_item))
        
        # Limit to 24 total buttons
        button_count = 0
        for item_type, item in all_items[:24]:
            if item_type == "carousel":
                carousel_message_id = item.get("message_id")
                button_label = item.get("button_label", "Carousel")
                
                # Truncate label if too long (Discord limit is 80 chars)
                if len(button_label) > 80:
                    button_label = button_label[:77] + "..."
                
                # Determine row (5 buttons per row)
                row = button_count // 5
                
                button = discord.ui.Button(
                    label=button_label,
                    style=discord.ButtonStyle.primary,
                    row=row,
                    custom_id=f"selector_{selector_message_id}_carousel_{carousel_message_id}"
                )
                
                # Create callback for this button - need to capture carousel_message_id in closure
                async def make_callback(interaction: Interaction, carousel_id=carousel_message_id):
                    await self._open_carousel(interaction, carousel_id)
                
                button.callback = make_callback
                self.add_item(button)
                button_count += 1
            elif item_type == "link":
                channel_id = item.get("channel_id")
                button_label = item.get("button_label", "Link")
                
                # Truncate label if too long (Discord limit is 80 chars)
                if len(button_label) > 80:
                    button_label = button_label[:77] + "..."
                
                # Determine row (5 buttons per row)
                row = button_count // 5
                
                # Create link button (discord.ButtonStyle.link requires url parameter)
                # We'll need to construct the Discord channel link URL
                # Format: https://discord.com/channels/{guild_id}/{channel_id}
                # But we need guild_id - we'll get it from the selector
                guild_id = selector.get("guild_id")
                if guild_id:
                    url = f"https://discord.com/channels/{guild_id}/{channel_id}"
                else:
                    # Fallback: try to get from cog's bot if available
                    url = None
                    if self.cog.bot and selector.get("channel_id"):
                        # Try to get guild from the selector's channel
                        try:
                            selector_channel = self.cog.bot.get_channel(selector.get("channel_id"))
                            if selector_channel and selector_channel.guild:
                                url = f"https://discord.com/channels/{selector_channel.guild.id}/{channel_id}"
                        except:
                            pass
                    
                    if not url:
                        # Can't create link button without guild_id, skip it
                        continue
                
                button = discord.ui.Button(
                    label=button_label,
                    style=discord.ButtonStyle.link,
                    url=url,
                    row=row
                )
                self.add_item(button)
                button_count += 1
        
        # Add admin button on the last row
        # Calculate which row the admin button should be on
        admin_row = (button_count // 5) if button_count > 0 else 0
        # Ensure admin button fits (max 5 rows, and we have space since max is 24 buttons)
        if admin_row >= 5:
            admin_row = 4  # Max 5 rows
        
        admin_button = discord.ui.Button(
            label="⚙️ Admin",
            style=discord.ButtonStyle.secondary,
            row=admin_row,
            custom_id=f"selector_admin_{selector_message_id}"
        )
        admin_button.callback = self.on_admin_menu
        self.add_item(admin_button)
    
    async def on_admin_menu(self, interaction: Interaction):
        """Open admin menu for the selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to manage selectors.", ephemeral=True)
            return
        
        view = SelectorAdminView(self.cog, self.selector_message_id)
        await interaction.response.send_message("**Selector Admin Menu**\n\nSelect an action:", view=view, ephemeral=True)
    
    async def _open_carousel(self, interaction: Interaction, carousel_message_id: int):
        """Open the carousel when a button is clicked (works for both ephemeral and standard carousels)."""
        carousel = self.cog.config.get_carousel(carousel_message_id)
        if not carousel:
            await interaction.response.send_message("❌ Carousel not found.", ephemeral=True)
            return
        
        # Get the first page
        pages = carousel.get("pages", [])
        if not pages:
            await interaction.response.send_message("❌ This carousel has no pages.", ephemeral=True)
            return
        
        # Check if carousel is in ephemeral mode or standard mode
        is_ephemeral = carousel.get("ephemeral_mode", False)
        
        if is_ephemeral:
            # Use ephemeral carousel embed and view
            page = pages[0]
            embed = discord.Embed(
                title=carousel.get("ephemeral_title", "📚 Lore Carousel"),
                description=carousel.get("ephemeral_description", "Click the button below to start exploring!"),
                color=0x5865F2
            )
            
            # Use ephemeral image if available, otherwise use first page image
            image_url = carousel.get("ephemeral_image_url")
            if not image_url and page.get("image_url"):
                image_url = page["image_url"]
            if image_url:
                embed.set_image(url=image_url)
            
            # Create the ephemeral carousel view
            view = EphemeralCarouselView(self.cog, carousel_message_id, 0)
        else:
            # For standard carousels, show them in ephemeral mode (privately) when opened from selector
            page = pages[0]
            embed = discord.Embed(
                title=page.get("header", "Untitled"),
                description=page.get("body", ""),
                color=discord.Color.blue()
            )
            
            if page.get("image_url"):
                embed.set_image(url=page["image_url"])
            
            embed.set_footer(text=f"Page 1 of {len(pages)}")
            
            # Create the ephemeral carousel view (works for both types)
            view = EphemeralCarouselView(self.cog, carousel_message_id, 0)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class SelectorAdminView(discord.ui.View):
    """Admin view for managing carousel selectors."""
    
    def __init__(self, cog, selector_message_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
    
    @discord.ui.button(label="➕ Add Carousel", style=discord.ButtonStyle.success, row=0)
    async def add_carousel(self, interaction: Interaction, button: discord.ui.Button):
        """Add a carousel to the selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        # Get all carousels for this guild (not just ephemeral)
        carousels = self.cog.config.get_carousels_by_guild(interaction.guild.id, bot=self.cog.bot, ephemeral_only=False)
        
        if not carousels:
            await interaction.response.send_message("❌ No carousels found in this server. Create a carousel first.", ephemeral=True)
            return
        
        view = AddCarouselToSelectorView(self.cog, self.selector_message_id, interaction.guild.id)
        await interaction.response.send_message("**Add Carousel to Selector**\n\nSelect a carousel to add:", view=view, ephemeral=True)
    
    @discord.ui.button(label="✏️ Edit Embed", style=discord.ButtonStyle.primary, row=0)
    async def edit_embed(self, interaction: Interaction, button: discord.ui.Button):
        """Edit the selector embed."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.response.send_message("❌ Selector not found.", ephemeral=True)
            return
        
        # Show modal for text fields (title/description)
        # For image upload, users need to use the /lore selector edit-image command
        modal = EditSelectorEmbedModal(self.cog, self.selector_message_id, selector)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🏷️ Edit Button Label", style=discord.ButtonStyle.secondary, row=0)
    async def edit_button_label(self, interaction: Interaction, button: discord.ui.Button):
        """Edit a button label."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.response.send_message("❌ Selector not found.", ephemeral=True)
            return
        
        carousels = selector.get("carousels", [])
        if not carousels:
            await interaction.response.send_message("❌ No carousels in this selector to edit.", ephemeral=True)
            return
        
        # Show dropdown to select which button to edit
        view = SelectButtonToEditView(self.cog, self.selector_message_id, carousels)
        await interaction.response.send_message("**Edit Button Label**\n\nSelect a button to edit:", view=view, ephemeral=True)
    
    @discord.ui.button(label="➖ Remove Carousel", style=discord.ButtonStyle.danger, row=1)
    async def remove_carousel(self, interaction: Interaction, button: discord.ui.Button):
        """Remove a carousel from the selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.response.send_message("❌ Selector not found.", ephemeral=True)
            return
        
        carousels = selector.get("carousels", [])
        if not carousels:
            await interaction.response.send_message("❌ No carousels in this selector to remove.", ephemeral=True)
            return
        
        # Show dropdown to select which carousel to remove
        view = SelectCarouselToRemoveView(self.cog, self.selector_message_id, carousels)
        await interaction.response.send_message("**Remove Carousel**\n\nSelect a carousel to remove:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🔗 Add Link", style=discord.ButtonStyle.success, row=1)
    async def add_link(self, interaction: Interaction, button: discord.ui.Button):
        """Add a link button to the selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.response.send_message("❌ Selector not found.", ephemeral=True)
            return
        
        # Show modal for channel selection and button label
        modal = AddLinkModal(self.cog, self.selector_message_id, interaction.guild.id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="➖ Remove Link", style=discord.ButtonStyle.danger, row=1)
    async def remove_link(self, interaction: Interaction, button: discord.ui.Button):
        """Remove a link button from the selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.response.send_message("❌ Selector not found.", ephemeral=True)
            return
        
        links = selector.get("links", [])
        if not links:
            await interaction.response.send_message("❌ No links in this selector to remove.", ephemeral=True)
            return
        
        # Show dropdown to select which link to remove
        view = SelectLinkToRemoveView(self.cog, self.selector_message_id, links)
        await interaction.response.send_message("**Remove Link**\n\nSelect a link to remove:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Delete Selector", style=discord.ButtonStyle.danger, row=2)
    async def delete_selector(self, interaction: Interaction, button: discord.ui.Button):
        """Delete the entire selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        view = ConfirmDeleteSelectorView(self.cog, self.selector_message_id)
        await interaction.response.send_message("⚠️ **Delete Selector**\n\nAre you sure you want to delete this selector? This action cannot be undone.", view=view, ephemeral=True)


class AddCarouselToSelectorView(discord.ui.View):
    """View with dropdown to select a carousel and modal for button label."""
    
    def __init__(self, cog, selector_message_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.guild_id = guild_id
        
        # Get all carousels for this guild (not just ephemeral)
        carousels = cog.config.get_carousels_by_guild(guild_id, bot=cog.bot, ephemeral_only=False)
        
        if not carousels:
            # No carousels available - we'll handle this in the callback
            self.carousels = []
            return
        
        self.carousels = carousels
        
        # Create dropdown with carousel options
        options = []
        for carousel in carousels[:25]:  # Discord limit
            message_id = carousel.get("message_id")
            # Get carousel title/name - prioritize first page header over ephemeral_title
            # This ensures we show the actual content name, not just the default "📚 Lore Carousel"
            title = "Untitled Carousel"
            
            # First try to get title from first page header (most descriptive and accurate)
            if carousel.get("pages") and len(carousel["pages"]) > 0:
                first_page = carousel["pages"][0]
                page_header = first_page.get("header", "").strip()
                if page_header:
                    title = page_header
                else:
                    # No header in first page, fall back to ephemeral_title
                    ephemeral_title = carousel.get("ephemeral_title", "").strip()
                    if ephemeral_title:
                        title = ephemeral_title
            else:
                # No pages, use ephemeral_title if available
                ephemeral_title = carousel.get("ephemeral_title", "").strip()
                if ephemeral_title:
                    title = ephemeral_title
            
            display_name = f"{title} (ID: {message_id})"
            
            # Truncate if too long (Discord limit is 100 chars for option label)
            if len(display_name) > 100:
                display_name = display_name[:97] + "..."
            
            options.append(discord.SelectOption(
                label=display_name,
                value=str(message_id),
                description=f"Add {title[:50]}"
            ))
        
        select = discord.ui.Select(
            placeholder="Select a carousel to add...",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle carousel selection - show modal for button label."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        try:
            carousel_id = int(interaction.data["values"][0])
        except (ValueError, KeyError, IndexError):
            await interaction.response.send_message("❌ Invalid selection.", ephemeral=True)
            return
        
        # Show modal for button label
        modal = ButtonLabelModal(self.cog, self.selector_message_id, carousel_id)
        await interaction.response.send_modal(modal)


class ButtonLabelModal(discord.ui.Modal, title="Add Carousel to Selector"):
    """Modal for entering the button label."""
    
    def __init__(self, cog, selector_message_id: int, carousel_id: int):
        super().__init__()
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.carousel_id = carousel_id
        
        # Get carousel to suggest a label
        carousel = cog.config.get_carousel(carousel_id)
        suggested_label = "Carousel"
        if carousel:
            if carousel.get("ephemeral_title"):
                suggested_label = carousel.get("ephemeral_title")
            elif carousel.get("pages"):
                first_page = carousel["pages"][0]
                suggested_label = first_page.get("header", "Carousel")
        
        self.button_label_input = discord.ui.TextInput(
            label="Button Label",
            placeholder="Text for the button (max 80 characters)",
            default=suggested_label[:80],
            required=True,
            max_length=80,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.button_label_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        button_label = self.button_label_input.value.strip()
        if not button_label:
            await interaction.followup.send("❌ Button label is required.", ephemeral=True)
            return
        
        # Validate carousel exists
        carousel = self.cog.config.get_carousel(self.carousel_id)
        if not carousel:
            await interaction.followup.send(f"❌ Carousel not found.", ephemeral=True)
            return
        
        # Truncate label if too long
        if len(button_label) > 80:
            button_label = button_label[:77] + "..."
        
        # Add carousel to selector
        try:
            self.cog.config.add_carousel_to_selector(self.selector_message_id, self.carousel_id, button_label)
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return
        
        # Update the selector message
        selector = self.cog.config.get_selector(self.selector_message_id)
        channel = get_channel_or_thread(interaction.guild, selector["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(self.selector_message_id)
                embed = discord.Embed(
                    title=selector.get("title", "📚 Lore Carousels"),
                    description=selector.get("description", "Select a carousel to explore:"),
                    color=0x5865F2
                )
                image_url = selector.get("image_url")
                if image_url:
                    embed.set_image(url=image_url)
                embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
                
                view = CarouselSelectorView(self.cog, self.selector_message_id)
                await message.edit(embed=embed, view=view)
                self.cog.bot.add_view(view, message_id=self.selector_message_id)
                
                await interaction.followup.send(f"✅ Carousel added to selector! The selector has been updated.", ephemeral=True)
            except discord.NotFound:
                await interaction.followup.send(f"✅ Carousel added to selector, but the selector message was not found.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"✅ Carousel added to selector, but failed to update message: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Carousel added to selector, but channel not found.", ephemeral=True)


class SelectCarouselToRemoveView(discord.ui.View):
    """View with dropdown to select which carousel to remove from selector."""
    
    def __init__(self, cog, selector_message_id: int, carousels: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.carousels = carousels
        
        # Create dropdown with carousel options
        options = []
        for carousel_item in carousels:
            carousel_id = carousel_item.get("message_id")
            button_label = carousel_item.get("button_label", "Carousel")
            # Get carousel title for display
            carousel = cog.config.get_carousel(carousel_id)
            if carousel and carousel.get("pages"):
                first_page = carousel["pages"][0]
                display_name = f"{button_label} (ID: {carousel_id})"
            else:
                display_name = f"{button_label} (ID: {carousel_id})"
            
            # Truncate if too long (Discord limit is 100 chars for option label)
            if len(display_name) > 100:
                display_name = display_name[:97] + "..."
            
            options.append(discord.SelectOption(
                label=display_name,
                value=str(carousel_id),
                description=f"Remove {button_label}"
            ))
        
        select = discord.ui.Select(
            placeholder="Select a carousel to remove...",
            options=options[:25]  # Discord limit
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle carousel selection."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            carousel_id = int(interaction.data["values"][0])
        except (ValueError, KeyError, IndexError):
            await interaction.followup.send("❌ Invalid selection.", ephemeral=True)
            return
        
        # Find the carousel item to get the label
        carousel_item = next((item for item in self.carousels if item.get("message_id") == carousel_id), None)
        button_label = carousel_item.get("button_label", "Carousel") if carousel_item else "Carousel"
        
        # Remove carousel from selector
        try:
            self.cog.config.remove_carousel_from_selector(self.selector_message_id, carousel_id)
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return
        
        # Update the selector message
        selector = self.cog.config.get_selector(self.selector_message_id)
        if selector:
            channel = get_channel_or_thread(interaction.guild, selector["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(self.selector_message_id)
                    embed = discord.Embed(
                        title=selector.get("title", "📚 Lore Carousels"),
                        description=selector.get("description", "Select a carousel to explore:"),
                        color=0x5865F2
                    )
                    image_url = selector.get("image_url")
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
                    
                    view = CarouselSelectorView(self.cog, self.selector_message_id)
                    await message.edit(embed=embed, view=view)
                    self.cog.bot.add_view(view, message_id=self.selector_message_id)
                    
                    await interaction.followup.send(f"✅ Carousel '{button_label}' removed from selector!", ephemeral=True)
                except discord.NotFound:
                    await interaction.followup.send("✅ Carousel removed, but selector message not found.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"✅ Carousel removed, but failed to update message: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("✅ Carousel removed, but channel not found.", ephemeral=True)
        else:
            await interaction.followup.send("✅ Carousel removed.", ephemeral=True)


class AddLinkModal(discord.ui.Modal, title="Add Link to Selector"):
    """Modal for adding a link button to a selector."""
    
    def __init__(self, cog, selector_message_id: int, guild_id: int):
        super().__init__()
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.guild_id = guild_id
        
        self.channel_input = discord.ui.TextInput(
            label="Channel or Thread",
            placeholder="Mention (#channel), paste ID, or Discord link",
            required=True,
            max_length=200,
            style=discord.TextStyle.short
        )
        
        self.button_label_input = discord.ui.TextInput(
            label="Button Label",
            placeholder="Text for the button (max 80 characters)",
            required=True,
            max_length=80,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.channel_input)
        self.add_item(self.button_label_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not interaction.guild:
            await interaction.followup.send("❌ This can only be used in a server.", ephemeral=True)
            return
        
        channel_input = self.channel_input.value.strip()
        button_label = self.button_label_input.value.strip()
        
        if not button_label:
            await interaction.followup.send("❌ Button label is required.", ephemeral=True)
            return
        
        # Parse channel from input (could be mention, ID, Discord link, or name)
        channel_id = None
        
        # Try to extract from mention format: <#123456789>
        if channel_input.startswith("<#") and channel_input.endswith(">"):
            try:
                channel_id = int(channel_input[2:-1])
            except ValueError:
                pass
        
        # Try to extract from Discord link format: https://discord.com/channels/{guild_id}/{channel_id}
        if not channel_id:
            # Match Discord channel links (both full URLs and partial paths)
            # Pattern: discord.com/channels/{guild_id}/{channel_id}
            link_pattern = r'(?:https?://)?(?:www\.)?discord\.com/channels/(\d+)/(\d+)'
            match = re.search(link_pattern, channel_input)
            if match:
                try:
                    # Extract channel_id (second capture group)
                    channel_id = int(match.group(2))
                except (ValueError, IndexError):
                    pass
        
        # Try to parse as direct ID
        if not channel_id:
            try:
                channel_id = int(channel_input)
            except ValueError:
                pass
        
        # Try to find by name
        if not channel_id:
            # Search channels and threads
            channel = None
            for ch in interaction.guild.channels:
                if isinstance(ch, (discord.TextChannel, discord.ForumChannel)) and ch.name.lower() == channel_input.lower():
                    channel = ch
                    break
            
            if not channel:
                # Try threads
                for ch in interaction.guild.channels:
                    if isinstance(ch, (discord.TextChannel, discord.ForumChannel)):
                        for thread in ch.threads:
                            if thread.name.lower() == channel_input.lower():
                                channel = thread
                                break
                        if channel:
                            break
            
            if channel:
                channel_id = channel.id
        
        if not channel_id:
            await interaction.followup.send("❌ Could not find channel or thread. Please mention it (e.g., #channel-name), provide the channel ID, or paste a Discord channel link.", ephemeral=True)
            return
        
        # Verify channel exists
        channel = get_channel_or_thread(interaction.guild, channel_id)
        if not channel:
            await interaction.followup.send("❌ Channel or thread not found. Make sure it exists and the bot can access it.", ephemeral=True)
            return
        
        # Truncate label if too long
        if len(button_label) > 80:
            button_label = button_label[:77] + "..."
        
        # Add link to selector
        try:
            self.cog.config.add_link_to_selector(self.selector_message_id, channel_id, button_label)
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return
        
        # Update the selector message
        selector = self.cog.config.get_selector(self.selector_message_id)
        if selector:
            channel_obj = get_channel_or_thread(interaction.guild, selector["channel_id"])
            if channel_obj:
                try:
                    message = await channel_obj.fetch_message(self.selector_message_id)
                    embed = discord.Embed(
                        title=selector.get("title", "📚 Lore Carousels"),
                        description=selector.get("description", "Select a carousel to explore:"),
                        color=0x5865F2
                    )
                    image_url = selector.get("image_url")
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
                    
                    view = CarouselSelectorView(self.cog, self.selector_message_id)
                    await message.edit(embed=embed, view=view)
                    self.cog.bot.add_view(view, message_id=self.selector_message_id)
                    
                    await interaction.followup.send(f"✅ Link button '{button_label}' added to selector! It will link to {channel.mention}.", ephemeral=True)
                except discord.NotFound:
                    await interaction.followup.send(f"✅ Link added to selector, but selector message not found.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"✅ Link added to selector, but failed to update message: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Link added to selector, but channel not found.", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Link added to selector.", ephemeral=True)


class SelectLinkToRemoveView(discord.ui.View):
    """View with dropdown to select which link to remove from selector."""
    
    def __init__(self, cog, selector_message_id: int, links: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.links = links
        
        # Create dropdown with link options
        options = []
        for link_item in links:
            channel_id = link_item.get("channel_id")
            button_label = link_item.get("button_label", "Link")
            
            # Try to get channel name for display
            channel_name = f"Channel {channel_id}"
            if self.cog.bot:
                try:
                    # Try to find channel in any guild
                    for guild in self.cog.bot.guilds:
                        channel = get_channel_or_thread(guild, channel_id)
                        if channel:
                            channel_name = f"#{channel.name}" if hasattr(channel, 'name') else f"Thread {channel_id}"
                            break
                except:
                    pass
            
            display_name = f"{button_label} → {channel_name}"
            
            # Truncate if too long (Discord limit is 100 chars for option label)
            if len(display_name) > 100:
                display_name = display_name[:97] + "..."
            
            options.append(discord.SelectOption(
                label=display_name,
                value=str(channel_id),
                description=f"Remove {button_label}"
            ))
        
        select = discord.ui.Select(
            placeholder="Select a link to remove...",
            options=options[:25]  # Discord limit
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle link selection."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            channel_id = int(interaction.data["values"][0])
        except (ValueError, KeyError, IndexError):
            await interaction.followup.send("❌ Invalid selection.", ephemeral=True)
            return
        
        # Find the link item to get the label
        link_item = next((item for item in self.links if item.get("channel_id") == channel_id), None)
        button_label = link_item.get("button_label", "Link") if link_item else "Link"
        
        # Remove link from selector
        try:
            self.cog.config.remove_link_from_selector(self.selector_message_id, channel_id)
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return
        
        # Update the selector message
        selector = self.cog.config.get_selector(self.selector_message_id)
        if selector:
            channel = get_channel_or_thread(interaction.guild, selector["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(self.selector_message_id)
                    embed = discord.Embed(
                        title=selector.get("title", "📚 Lore Carousels"),
                        description=selector.get("description", "Select a carousel to explore:"),
                        color=0x5865F2
                    )
                    image_url = selector.get("image_url")
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
                    
                    view = CarouselSelectorView(self.cog, self.selector_message_id)
                    await message.edit(embed=embed, view=view)
                    self.cog.bot.add_view(view, message_id=self.selector_message_id)
                    
                    await interaction.followup.send(f"✅ Link button '{button_label}' removed from selector!", ephemeral=True)
                except discord.NotFound:
                    await interaction.followup.send("✅ Link removed, but selector message not found.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"✅ Link removed, but failed to update message: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("✅ Link removed, but channel not found.", ephemeral=True)
        else:
            await interaction.followup.send("✅ Link removed.", ephemeral=True)


class RepostCarouselView(discord.ui.View):
    """View with dropdown to select which carousel to repost."""
    
    def __init__(self, cog, target_channel: Union[discord.TextChannel, discord.Thread], carousels: List[Dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.target_channel = target_channel
        self.carousels = carousels
        
        # Create carousel dropdown
        carousel_options = []
        for carousel in carousels[:25]:  # Discord limit
            message_id = carousel.get("message_id")
            # Get carousel title/name - prioritize first page header over ephemeral_title
            title = "Untitled Carousel"
            
            # First try to get title from first page header
            if carousel.get("pages") and len(carousel["pages"]) > 0:
                first_page = carousel["pages"][0]
                page_header = first_page.get("header", "").strip()
                if page_header:
                    title = page_header
                else:
                    # No header in first page, fall back to ephemeral_title
                    ephemeral_title = carousel.get("ephemeral_title", "").strip()
                    if ephemeral_title:
                        title = ephemeral_title
            else:
                # No pages, use ephemeral_title if available
                ephemeral_title = carousel.get("ephemeral_title", "").strip()
                if ephemeral_title:
                    title = ephemeral_title
            
            display_name = f"{title} (ID: {message_id})"
            
            # Truncate if too long (Discord limit is 100 chars for option label)
            if len(display_name) > 100:
                display_name = display_name[:97] + "..."
            
            carousel_options.append(discord.SelectOption(
                label=display_name,
                value=str(message_id),
                description=f"Repost {title[:50]}"
            ))
        
        if carousel_options:
            carousel_select = discord.ui.Select(
                placeholder="Select a carousel to repost...",
                options=carousel_options[:25],  # Discord limit
                row=0
            )
            carousel_select.callback = self.on_carousel_select
            self.add_item(carousel_select)
    
    async def on_carousel_select(self, interaction: Interaction):
        """Handle carousel selection and repost it."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            message_id = int(interaction.data["values"][0])
        except (ValueError, KeyError, IndexError):
            await interaction.followup.send("❌ Invalid selection.", ephemeral=True)
            return
        
        # Get carousel data
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel:
            await interaction.followup.send("❌ Carousel not found.", ephemeral=True)
            return
        
        pages = carousel.get("pages", [])
        if not pages:
            await interaction.followup.send("❌ Carousel has no pages.", ephemeral=True)
            return
        
        # Repost the carousel
        await self._repost_carousel(interaction, carousel, pages, self.target_channel)
    
    async def _repost_carousel(self, interaction: Interaction, carousel: Dict, pages: List[Dict], target_channel: Union[discord.TextChannel, discord.Thread]):
        """Actually repost the carousel to the target channel."""
        # Note: interaction is already deferred in on_carousel_select, so use followup
        try:
            # Determine if carousel is in ephemeral mode
            is_ephemeral = carousel.get("ephemeral_mode", False)
            
            if is_ephemeral:
                # For ephemeral carousels, create the initial "Start Here" message
                embed = discord.Embed(
                    title=carousel.get("ephemeral_title", "📚 Lore Carousel"),
                    description=carousel.get("ephemeral_description", "Click the button below to start exploring!"),
                    color=0x5865F2
                )
                
                # Use ephemeral image if available, otherwise use first page image
                image_url = carousel.get("ephemeral_image_url")
                if not image_url and pages[0].get("image_url"):
                    image_url = pages[0]["image_url"]
                if image_url:
                    embed.set_image(url=image_url)
            else:
                # For standard carousels, show the first page
                first_page = pages[0]
                embed = discord.Embed(
                    title=first_page.get("header", "Untitled"),
                    description=first_page.get("body", ""),
                    color=discord.Color.blue()
                )
                
                if first_page.get("image_url"):
                    embed.set_image(url=first_page["image_url"])
                
                embed.set_footer(text=f"Page 1 of {len(pages)}")
            
            # Send the message first (without view, since we need the message_id)
            message = await target_channel.send(embed=embed)
            
            # Save the carousel with the new message_id and channel FIRST
            # This ensures the view can find the carousel data when it's created
            # For reposts, store a reference to the original instead of duplicating pages
            # BUT: if the original doesn't exist, store pages directly as a fallback
            original_message_id = carousel.get("message_id")
            
            # Check if original exists and has pages (to determine if we can use reference)
            original_exists = False
            if original_message_id:
                original_carousel = self.cog.config.get_carousel(original_message_id, _resolving_repost=True)
                original_exists = original_carousel and original_carousel.get("pages")
            
            # Get ephemeral settings from original to preserve them
            ephemeral_title = carousel.get("ephemeral_title", "📚 Lore Carousel")
            ephemeral_description = carousel.get("ephemeral_description", "Click the button below to start exploring!")
            ephemeral_button_label = carousel.get("ephemeral_button_label", "Start Here")
            ephemeral_image_url = carousel.get("ephemeral_image_url")
            
            # If original exists, use reference (store empty pages)
            # If original doesn't exist, store pages directly as fallback
            pages_to_store = [] if original_exists else pages
            stored_original_id = original_message_id if original_exists else None
            
            self.cog.config.add_carousel(
                target_channel.id,
                pages_to_store,  # Empty if using reference, full pages if original missing
                message.id,
                ephemeral_mode=is_ephemeral,
                guild_id=interaction.guild.id if interaction.guild else None,
                original_message_id=stored_original_id  # Only set if original exists
            )
            
            # Preserve ephemeral settings from original after creating the entry
            if is_ephemeral:
                self.cog.config.set_ephemeral_text(
                    message.id,
                    ephemeral_title,
                    ephemeral_description,
                    ephemeral_button_label,
                    ephemeral_image_url
                )
            
            # Register the message mapping
            self.cog.carousel_messages[message.id] = target_channel.id
            
            # Now create the view with the actual message_id (after carousel is saved)
            if is_ephemeral:
                # For ephemeral carousels, use StartCarouselView which has the "Start Here" button
                view = StartCarouselView(self.cog, message.id)
                # Register the view with the bot for persistence (needed for ephemeral carousels)
                # Pass message_id to ensure proper registration
                self.cog.bot.add_view(view, message_id=message.id)
            else:
                # For standard carousels, use LoreCarouselView which has page navigation
                view = LoreCarouselView(self.cog, message.id, 0)
                # For views with select menus, editing the message makes it persistent
                # But we can also try registering it (some views work with this)
                try:
                    self.cog.bot.add_view(view, message_id=message.id)
                except:
                    # If registration fails, editing the message should still work
                    pass
            
            # Edit the message with the view (this makes it persistent)
            await message.edit(view=view)
            
            # Get carousel title for confirmation message
            carousel_title = "Untitled Carousel"
            if pages and pages[0].get("header"):
                carousel_title = pages[0]["header"]
            elif carousel.get("ephemeral_title"):
                carousel_title = carousel.get("ephemeral_title")
            
            await interaction.followup.send(
                f"✅ Successfully reposted carousel **{carousel_title}** to {target_channel.mention}!",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to send messages in that channel. Please check the bot's permissions.",
                ephemeral=True
            )
        except Exception as e:
            import traceback
            error_msg = f"❌ Error reposting carousel: {str(e)}"
            print(f"[lore_carousel] Error in repost: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(error_msg, ephemeral=True)


class SelectCarouselToDeleteView(discord.ui.View):
    """View with dropdown to select which carousel to delete."""
    
    def __init__(self, cog, carousels: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.carousels = carousels
        
        # Create dropdown with carousel options
        options = []
        for carousel in carousels[:25]:  # Discord limit
            message_id = carousel.get("message_id")
            # Get carousel title/name from first page
            title = "Untitled Carousel"
            if carousel.get("pages"):
                first_page = carousel["pages"][0]
                title = first_page.get("header", "Untitled Carousel")
            
            # Use ephemeral title if available
            if carousel.get("ephemeral_title"):
                title = carousel.get("ephemeral_title")
            
            # Get channel info for display
            channel_id = carousel.get("channel_id")
            channel_info = ""
            if channel_id and self.cog.bot:
                try:
                    guild = self.cog.bot.get_guild(carousel.get("guild_id", 0))
                    if guild:
                        channel = get_channel_or_thread(guild, channel_id)
                        if channel:
                            channel_info = f" in #{channel.name}"
                except:
                    pass
            
            display_name = f"{title} (ID: {message_id})"
            
            # Truncate if too long (Discord limit is 100 chars for option label)
            if len(display_name) > 100:
                display_name = display_name[:97] + "..."
            
            description = f"Delete {title[:50]}{channel_info}"
            if len(description) > 100:
                description = description[:97] + "..."
            
            options.append(discord.SelectOption(
                label=display_name,
                value=str(message_id),
                description=description
            ))
        
        select = discord.ui.Select(
            placeholder="Select a carousel to delete...",
            options=options[:25]  # Discord limit
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle carousel selection."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        try:
            message_id = int(interaction.data["values"][0])
        except (ValueError, KeyError, IndexError):
            await interaction.response.send_message("❌ Invalid selection.", ephemeral=True)
            return
        
        # Get carousel info for confirmation
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel:
            await interaction.response.send_message("❌ Carousel not found.", ephemeral=True)
            return
        
        # Get carousel title
        title = "Untitled Carousel"
        if carousel.get("pages"):
            first_page = carousel["pages"][0]
            title = first_page.get("header", "Untitled Carousel")
        if carousel.get("ephemeral_title"):
            title = carousel.get("ephemeral_title")
        
        # Get channel info
        channel_id = carousel.get("channel_id")
        channel_info = ""
        if channel_id:
            try:
                channel = get_channel_or_thread(interaction.guild, channel_id)
                if channel:
                    channel_info = f" in {channel.mention}"
            except:
                pass
        
        # Show confirmation view
        confirm_view = ConfirmDeleteCarouselView(self.cog, message_id, title, channel_info)
        await interaction.response.edit_message(
            content=f"**⚠️ Confirm Deletion**\n\nAre you sure you want to delete **{title}**{channel_info}?\n\nThis action **cannot be undone** and will delete all pages in this carousel.",
            view=confirm_view
        )


class ConfirmDeleteCarouselView(discord.ui.View):
    """Confirmation view for deleting a carousel."""
    
    def __init__(self, cog, message_id: int, title: str, channel_info: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        self.title = title
        self.channel_info = channel_info
    
    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger, row=0)
    async def confirm_delete(self, interaction: Interaction, button: discord.ui.Button):
        """Confirm deletion of the carousel."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel:
            await interaction.followup.send("❌ Carousel not found.", ephemeral=True)
            return
        
        channel_id = carousel.get("channel_id")
        
        # Delete the carousel message if it exists
        if channel_id:
            try:
                channel = get_channel_or_thread(interaction.guild, channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(self.message_id)
                        await message.delete()
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        await interaction.followup.send("❌ Cannot delete the carousel message. Please delete it manually.", ephemeral=True)
                        return
            except:
                pass
        
        # Remove carousel from config
        self.cog.config.remove_carousel(self.message_id)
        self.cog.carousel_messages.pop(self.message_id, None)
        
        await interaction.followup.send(f"✅ Carousel **{self.title}**{self.channel_info} has been deleted.", ephemeral=True)
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel_delete(self, interaction: Interaction, button: discord.ui.Button):
        """Cancel deletion."""
        await interaction.response.edit_message(content="❌ Deletion cancelled.", view=None)


class EditSelectorEmbedView(discord.ui.View):
    """View for editing selector embed with file upload support."""
    
    def __init__(self, cog, selector_message_id: int, selector: Dict):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.selector = selector
    
    @discord.ui.button(label="📝 Edit Text", style=discord.ButtonStyle.primary)
    async def edit_text(self, interaction: Interaction, button: discord.ui.Button):
        """Open modal to edit text fields."""
        modal = EditSelectorEmbedModal(self.cog, self.selector_message_id, self.selector)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📷 Upload Image", style=discord.ButtonStyle.secondary)
    async def upload_image(self, interaction: Interaction, button: discord.ui.Button):
        """Prompt for image upload."""
        selector = self.cog.config.get_selector(self.selector_message_id)
        if selector:
            selector_id = selector.get("message_id")
            await interaction.response.send_message(
                f"**Upload Image**\n\n"
                f"Use the command `/lore selector edit-image` with an image attachment to update the selector image.\n\n"
                f"**Selector Message ID:** `{selector_id}`\n"
                f"Use: `/lore selector edit-image selector_message_id:{selector_id}` and attach an image.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Selector not found.", ephemeral=True)


class EditSelectorEmbedModal(discord.ui.Modal, title="Edit Selector Embed"):
    """Modal for editing the selector embed with file upload support."""
    
    def __init__(self, cog, selector_message_id: int, selector: Dict):
        super().__init__()
        self.cog = cog
        self.selector_message_id = selector_message_id
        
        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="Title for the selector embed",
            default=selector.get("title", "📚 Lore Carousels"),
            required=True,
            max_length=256,
            style=discord.TextStyle.short
        )
        
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Description for the selector embed",
            default=selector.get("description", "Select a carousel to explore:"),
            required=True,
            max_length=2000,
            style=discord.TextStyle.paragraph
        )
        
        # File upload via Label + FileUpload (type 18 + 19)
        self.image_upload = discord.ui.Label(
            text="Image (Optional)",
            description="Upload an image to set as the selector embed image.",
            component=discord.ui.FileUpload(
                custom_id="selector_image_upload",
                required=False,
                min_values=0,
                max_values=1,
            ),
        )
        
        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.image_upload)
    
    async def on_submit(self, interaction: Interaction):
        # Defer immediately to keep interaction alive during file processing
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        title = self.title_input.value.strip()
        description = self.description_input.value.strip()
        
        if not title or not description:
            await interaction.followup.send("❌ Title and description are required.", ephemeral=True)
            return
        
        # Handle file upload
        image_url = None
        assert isinstance(self.image_upload.component, discord.ui.FileUpload)
        
        if self.image_upload.component.values:
            # File was uploaded
            attachment: discord.Attachment = self.image_upload.component.values[0]
            # Validate it's an image
            if attachment.content_type and attachment.content_type.startswith("image/"):
                image_url = attachment.url
            else:
                await interaction.followup.send("❌ Uploaded file must be an image.", ephemeral=True)
                return
        
        # If no file upload, preserve existing image
        if not image_url:
            selector = self.cog.config.get_selector(self.selector_message_id)
            if selector:
                image_url = selector.get("image_url")
        
        # Update selector
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.followup.send("❌ Selector not found.", ephemeral=True)
            return
        
        channel = get_channel_or_thread(interaction.guild, selector["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(self.selector_message_id)
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=0x5865F2
                )
                if image_url:
                    embed.set_image(url=image_url)
                embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
                
                view = CarouselSelectorView(self.cog, self.selector_message_id)
                await message.edit(embed=embed, view=view)
                self.cog.bot.add_view(view, message_id=self.selector_message_id)
                
                # Update selector data
                self.cog.config.add_selector(
                    selector["channel_id"],
                    self.selector_message_id,
                    title,
                    description,
                    guild_id=selector.get("guild_id"),
                    image_url=image_url
                )
                
                await interaction.followup.send("✅ Selector embed updated!", ephemeral=True)
            except discord.NotFound:
                await interaction.followup.send("❌ Selector message not found.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to update selector: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)


class SelectButtonToEditView(discord.ui.View):
    """View with dropdown to select which button to edit."""
    
    def __init__(self, cog, selector_message_id: int, carousels: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.carousels = carousels
        
        # Create dropdown with button options
        options = []
        for carousel_item in carousels[:25]:  # Discord limit
            carousel_id = carousel_item.get("message_id")
            button_label = carousel_item.get("button_label", "Carousel")
            
            # Get carousel title for display
            carousel = cog.config.get_carousel(carousel_id)
            if carousel and carousel.get("pages"):
                first_page = carousel["pages"][0]
                display_name = f"{button_label} (ID: {carousel_id})"
            else:
                display_name = f"{button_label} (ID: {carousel_id})"
            
            # Truncate if too long (Discord limit is 100 chars for option label)
            if len(display_name) > 100:
                display_name = display_name[:97] + "..."
            
            options.append(discord.SelectOption(
                label=display_name,
                value=str(carousel_id),
                description=f"Edit '{button_label}'"
            ))
        
        select = discord.ui.Select(
            placeholder="Select a button to edit...",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle button selection - show modal for new label."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        try:
            carousel_id = int(interaction.data["values"][0])
        except (ValueError, KeyError, IndexError):
            await interaction.response.send_message("❌ Invalid selection.", ephemeral=True)
            return
        
        # Find the carousel item to get current label
        carousel_item = next((item for item in self.carousels if item.get("message_id") == carousel_id), None)
        if not carousel_item:
            await interaction.response.send_message("❌ Carousel not found in selector.", ephemeral=True)
            return
        
        current_label = carousel_item.get("button_label", "Carousel")
        
        # Show modal for new label (can't defer, need to send modal directly)
        modal = EditButtonLabelModal(self.cog, self.selector_message_id, carousel_id, current_label)
        await interaction.response.send_modal(modal)


class EditButtonLabelModal(discord.ui.Modal, title="Edit Button Label"):
    """Modal for editing a button label."""
    
    def __init__(self, cog, selector_message_id: int, carousel_id: int, current_label: str):
        super().__init__()
        self.cog = cog
        self.selector_message_id = selector_message_id
        self.carousel_id = carousel_id
        
        self.label_input = discord.ui.TextInput(
            label="Button Label",
            placeholder="Text for the button (max 80 characters)",
            default=current_label,
            required=True,
            max_length=80,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.label_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        new_label = self.label_input.value.strip()
        if not new_label:
            await interaction.followup.send("❌ Button label is required.", ephemeral=True)
            return
        
        # Truncate if too long
        if len(new_label) > 80:
            new_label = new_label[:77] + "..."
        
        # Update the button label in selector
        try:
            self.cog.config.add_carousel_to_selector(self.selector_message_id, self.carousel_id, new_label)
        except ValueError as e:
            await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            return
        
        # Update the selector message
        selector = self.cog.config.get_selector(self.selector_message_id)
        if selector:
            channel = get_channel_or_thread(interaction.guild, selector["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(self.selector_message_id)
                    embed = discord.Embed(
                        title=selector.get("title", "📚 Lore Carousels"),
                        description=selector.get("description", "Select a carousel to explore:"),
                        color=0x5865F2
                    )
                    image_url = selector.get("image_url")
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
                    
                    view = CarouselSelectorView(self.cog, self.selector_message_id)
                    await message.edit(embed=embed, view=view)
                    self.cog.bot.add_view(view, message_id=self.selector_message_id)
                    
                    await interaction.followup.send(f"✅ Button label updated to '{new_label}'!", ephemeral=True)
                except discord.NotFound:
                    await interaction.followup.send("✅ Button label updated, but selector message not found.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"✅ Button label updated, but failed to update message: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("✅ Button label updated, but channel not found.", ephemeral=True)
        else:
            await interaction.followup.send("✅ Button label updated.", ephemeral=True)


class ConfirmDeleteSelectorView(discord.ui.View):
    """Confirmation view for deleting a selector."""
    
    def __init__(self, cog, selector_message_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.selector_message_id = selector_message_id
    
    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger, row=0)
    async def confirm_delete(self, interaction: Interaction, button: discord.ui.Button):
        """Confirm deletion of the selector."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        selector = self.cog.config.get_selector(self.selector_message_id)
        if not selector:
            await interaction.followup.send(f"❌ Selector not found.", ephemeral=True)
            return
        
        # Delete the message if possible
        channel = get_channel_or_thread(interaction.guild, selector["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(self.selector_message_id)
                await message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await interaction.followup.send("❌ Cannot delete the selector message. Please delete it manually.", ephemeral=True)
                return
        
        # Remove from config
        self.cog.config.remove_selector(self.selector_message_id)
        
        await interaction.followup.send("✅ Selector deleted.", ephemeral=True)
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel_delete(self, interaction: Interaction, button: discord.ui.Button):
        """Cancel deletion."""
        await interaction.response.edit_message(content="❌ Deletion cancelled.", view=None)


class AddPageModal(discord.ui.Modal, title="Add Page"):
    """Modal for adding a new page to the carousel."""
    
    def __init__(self, cog, message_id: int):
        super().__init__()
        self.cog = cog
        self.message_id = message_id
        
        self.header_input = discord.ui.TextInput(
            label="Header",
            placeholder="Enter the page header/title",
            required=True,
            max_length=256,
            style=discord.TextStyle.short
        )
        
        self.body_input = discord.ui.TextInput(
            label="Body",
            placeholder="Enter the page content (max 4000 characters)",
            required=True,
            max_length=4000,
            style=discord.TextStyle.paragraph
        )
        
        # File upload via Label + FileUpload (type 18 + 19)
        self.image_upload = discord.ui.Label(
            text="Image (Optional)",
            description="Upload an image for this page.",
            component=discord.ui.FileUpload(
                custom_id="page_image_upload",
                required=False,
                min_values=0,
                max_values=1,
            ),
        )
        
        self.add_item(self.header_input)
        self.add_item(self.body_input)
        self.add_item(self.image_upload)
    
    async def on_submit(self, interaction: Interaction):
        # Defer immediately to keep interaction alive during file processing
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        header = self.header_input.value.strip()
        body = self.body_input.value.strip()
        
        if not header or not body:
            await interaction.followup.send("❌ Header and body are required.", ephemeral=True)
            return
        
        # Handle file upload
        image_url = None
        assert isinstance(self.image_upload.component, discord.ui.FileUpload)
        
        if self.image_upload.component.values:
            # File was uploaded
            attachment: discord.Attachment = self.image_upload.component.values[0]
            # Validate it's an image
            if attachment.content_type and attachment.content_type.startswith("image/"):
                image_url = attachment.url
            else:
                await interaction.followup.send("❌ Uploaded file must be an image.", ephemeral=True)
                return
        
        page_index = self.cog.config.add_page(self.message_id, header, body, image_url)
        
        # Update the carousel message if in standard mode
        carousel = self.cog.config.get_carousel(self.message_id)
        if carousel and not carousel.get("ephemeral_mode", False):
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                await self.cog.update_carousel_message(channel, message_id=self.message_id)
        
        await interaction.followup.send(f"✅ Added page: **{header}**", ephemeral=True)


class EphemeralConfigModal(discord.ui.Modal, title="Configure Ephemeral Carousel"):
    """Modal for configuring ephemeral mode carousel text."""
    
    def __init__(self, cog, message_id: int):
        super().__init__()
        self.cog = cog
        self.message_id = message_id
        
        # Get current values if they exist
        carousel = cog.config.get_carousel(message_id)
        current_title = carousel.get("ephemeral_title", "📚 Lore Carousel") if carousel else "📚 Lore Carousel"
        current_description = carousel.get("ephemeral_description", "Click the button below to start exploring!") if carousel else "Click the button below to start exploring!"
        current_button = carousel.get("ephemeral_button_label", "Start Here") if carousel else "Start Here"
        
        self.title_input = discord.ui.TextInput(
            label="Embed Title",
            placeholder="Title for the ephemeral carousel embed",
            default=current_title,
            required=True,
            max_length=256,
            style=discord.TextStyle.short
        )
        
        self.description_input = discord.ui.TextInput(
            label="Embed Description",
            placeholder="Description text for the ephemeral carousel embed",
            default=current_description,
            required=True,
            max_length=2000,
            style=discord.TextStyle.paragraph
        )
        
        self.button_label_input = discord.ui.TextInput(
            label="Button Label",
            placeholder="Text for the 'Start Here' button",
            default=current_button,
            required=True,
            max_length=80,
            style=discord.TextStyle.short
        )
        
        # File upload via Label + FileUpload (type 18 + 19)
        self.image_upload = discord.ui.Label(
            text="Image (Optional)",
            description="Upload an image to set as the ephemeral carousel embed image.",
            component=discord.ui.FileUpload(
                custom_id="ephemeral_image_upload",
                required=False,
                min_values=0,
                max_values=1,
            ),
        )
        
        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.button_label_input)
        self.add_item(self.image_upload)
    
    async def on_submit(self, interaction: Interaction):
        # Defer immediately to keep interaction alive during file processing
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        title = self.title_input.value.strip()
        description = self.description_input.value.strip()
        button_label = self.button_label_input.value.strip()
        
        if not title or not description or not button_label:
            await interaction.followup.send("❌ All fields are required.", ephemeral=True)
            return
        
        # Handle file upload
        image_url = None
        assert isinstance(self.image_upload.component, discord.ui.FileUpload)
        
        if self.image_upload.component.values:
            # File was uploaded
            attachment: discord.Attachment = self.image_upload.component.values[0]
            # Validate it's an image
            if attachment.content_type and attachment.content_type.startswith("image/"):
                image_url = attachment.url
            else:
                await interaction.followup.send("❌ Uploaded file must be an image.", ephemeral=True)
                return
        
        # Save the custom text and set ephemeral mode
        self.cog.config.set_ephemeral_text(self.message_id, title, description, button_label, image_url=image_url)
        self.cog.config.set_ephemeral_mode(self.message_id, True)
        
        # Update the carousel message with the new text
        carousel = self.cog.config.get_carousel(self.message_id)
        if carousel:
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(self.message_id)
                    start_embed = discord.Embed(
                        title=title,
                        description=description,
                        color=discord.Color.blue()
                    )
                    if image_url:
                        start_embed.set_image(url=image_url)
                    start_view = StartCarouselView(self.cog, self.message_id)
                    self.cog.bot.add_view(start_view)
                    await message.edit(embed=start_embed, view=start_view)
                    await interaction.followup.send("✅ Ephemeral carousel configured and updated!", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"❌ Failed to update message: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("❌ Channel not found.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Carousel not found.", ephemeral=True)


class EditPageModal(discord.ui.Modal):
    """Modal for editing an existing page."""
    
    def __init__(self, cog, message_id: int, page_index: int, current_page: Dict):
        super().__init__(title=f"Edit Page: {current_page.get('header', 'Untitled')[:40]}")
        self.cog = cog
        self.message_id = message_id
        self.page_index = page_index
        
        self.header_input = discord.ui.TextInput(
            label="Header",
            placeholder="Enter the page header/title",
            default=current_page.get("header", ""),
            required=True,
            max_length=256,
            style=discord.TextStyle.short
        )
        
        self.body_input = discord.ui.TextInput(
            label="Body",
            placeholder="Enter the page content (max 4000 characters)",
            default=current_page.get("body", ""),
            required=True,
            max_length=4000,
            style=discord.TextStyle.paragraph
        )
        
        # File upload via Label + FileUpload (type 18 + 19)
        self.image_upload = discord.ui.Label(
            text="Image (Optional)",
            description="Upload an image to replace the current page image, or leave empty to keep existing.",
            component=discord.ui.FileUpload(
                custom_id="edit_page_image_upload",
                required=False,
                min_values=0,
                max_values=1,
            ),
        )
        
        self.add_item(self.header_input)
        self.add_item(self.body_input)
        self.add_item(self.image_upload)
    
    async def on_submit(self, interaction: Interaction):
        # Defer immediately to keep interaction alive during file processing
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        header = self.header_input.value.strip()
        body = self.body_input.value.strip()
        
        if not header or not body:
            await interaction.followup.send("❌ Header and body are required.", ephemeral=True)
            return
        
        # Handle file upload
        image_url = None
        assert isinstance(self.image_upload.component, discord.ui.FileUpload)
        
        if self.image_upload.component.values:
            # File was uploaded
            attachment: discord.Attachment = self.image_upload.component.values[0]
            # Validate it's an image
            if attachment.content_type and attachment.content_type.startswith("image/"):
                image_url = attachment.url
            else:
                await interaction.followup.send("❌ Uploaded file must be an image.", ephemeral=True)
                return
        
        # If no file upload, preserve existing image
        if not image_url:
            carousel = self.cog.config.get_carousel(self.message_id)
            if carousel and carousel.get("pages") and self.page_index < len(carousel["pages"]):
                image_url = carousel["pages"][self.page_index].get("image_url")
        
        success = self.cog.config.update_page(self.message_id, self.page_index, header, body, image_url)
        
        if not success:
            await interaction.followup.send("❌ Failed to update page.", ephemeral=True)
            return
        
        # Update the carousel message if in standard mode
        carousel = self.cog.config.get_carousel(self.message_id)
        if carousel and not carousel.get("ephemeral_mode", False):
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                await self.cog.update_carousel_message(channel, message_id=self.message_id, page_index=self.page_index)
        
        await interaction.followup.send(f"✅ Updated page: **{header}**", ephemeral=True)


class AdminMenuView(discord.ui.View):
    """View for admin menu with buttons."""
    
    def __init__(self, cog, message_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        # Add toggle button with dynamic label based on current mode
        carousel = self.cog.config.get_carousel(self.message_id)
        ephemeral_mode = carousel.get("ephemeral_mode", False) if carousel else False
        toggle_label = "🔀 Switch to Ephemeral" if not ephemeral_mode else "🔀 Switch to Standard"
        toggle_button = discord.ui.Button(
            label=toggle_label,
            style=discord.ButtonStyle.secondary,
            row=1
        )
        # Create a wrapper to ensure correct signature
        async def toggle_callback(interaction: Interaction):
            await self.toggle_mode(interaction)
        toggle_button.callback = toggle_callback
        self.add_item(toggle_button)
    
    @discord.ui.button(label="➕ Add Page", style=discord.ButtonStyle.success, row=0)
    async def add_page(self, interaction: Interaction, button: discord.ui.Button):
        """Handle add page button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to add pages.", ephemeral=True)
            return
        
        modal = AddPageModal(self.cog, self.message_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✏️ Edit Page", style=discord.ButtonStyle.primary, row=0)
    async def edit_page(self, interaction: Interaction, button: discord.ui.Button):
        """Handle edit page button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to edit pages.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available to edit.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        if len(pages) == 1:
            # If only one page, edit it directly
            edit_modal = EditPageModal(self.cog, self.message_id, 0, pages[0])
            await interaction.response.send_modal(edit_modal)
        else:
            # Show select menu to choose which page to edit
            select_view = SelectPageView(self.cog, self.message_id, pages)
            await interaction.response.send_message("Select a page to edit:", view=select_view, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Remove Page", style=discord.ButtonStyle.danger, row=0)
    async def remove_page(self, interaction: Interaction, button: discord.ui.Button):
        """Handle remove page button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to remove pages.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available to remove.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        if len(pages) == 1:
            await interaction.response.send_message("❌ Cannot remove the last page. Delete the carousel instead with `/lore remove`.", ephemeral=True)
            return
        
        # Show select menu to choose which page to remove
        remove_view = RemovePageView(self.cog, self.message_id, pages)
        await interaction.response.send_message("Select a page to remove:", view=remove_view, ephemeral=True)
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: Interaction, button: discord.ui.Button):
        """Handle refresh button."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to refresh the carousel.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No carousel found.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Refresh the carousel message based on its mode
        channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
        if channel:
            ephemeral_mode = carousel.get("ephemeral_mode", False)
            if ephemeral_mode:
                # Refresh the "Start Here" button message (no change needed, but confirm)
                await interaction.followup.send("✅ Carousel data refreshed! The 'Start Here' button will show the latest pages.", ephemeral=True)
            else:
                # Refresh the standard carousel message
                await self.cog.update_carousel_message(channel, message_id=self.message_id)
                await interaction.followup.send("✅ Carousel refreshed!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
    
    async def toggle_mode(self, interaction: Interaction):
        """Handle toggle mode button - switch between standard and ephemeral."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to toggle carousel mode.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No carousel found.", ephemeral=True)
            return
        
        # Toggle the mode
        current_mode = carousel.get("ephemeral_mode", False)
        new_mode = not current_mode
        
        if new_mode:
            # Switching to ephemeral mode - show modal to configure text
            modal = EphemeralConfigModal(self.cog, self.message_id)
            await interaction.response.send_modal(modal)
        else:
            # Switching to standard mode - do it directly
            await interaction.response.defer(ephemeral=True)
            self.cog.config.set_ephemeral_mode(self.message_id, new_mode)
            
            # Update the message
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                try:
                    await self.cog.update_carousel_message(channel, message_id=self.message_id)
                    await interaction.followup.send("✅ Carousel converted to standard mode! The full carousel is now visible in the channel.", ephemeral=True)
                except discord.NotFound:
                    await interaction.followup.send("❌ Carousel message not found. It may have been deleted.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"❌ Error updating carousel: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send("❌ Channel not found.", ephemeral=True)


class SelectPageView(discord.ui.View):
    """View for selecting which page to edit."""
    
    def __init__(self, cog, message_id: int, pages: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        self.pages = pages
        
        # Create select menu with page options
        select = discord.ui.Select(
            placeholder="Select a page to edit...",
            options=[
                discord.SelectOption(
                    label=page.get("header", "Untitled")[:100],
                    value=str(i),
                    description=f"Page {i+1}"
                )
                for i, page in enumerate(pages)
            ]
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle page selection."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to edit pages.", ephemeral=True)
            return
        
        page_index = int(interaction.data["values"][0])
        current_page = self.pages[page_index]
        
        # Show edit modal
        edit_modal = EditPageModal(self.cog, self.message_id, page_index, current_page)
        await interaction.response.send_modal(edit_modal)


class RemovePageView(discord.ui.View):
    """View for selecting which page to remove."""
    
    def __init__(self, cog, message_id: int, pages: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        self.pages = pages
        
        # Create select menu with page options
        select = discord.ui.Select(
            placeholder="Select a page to remove...",
            options=[
                discord.SelectOption(
                    label=page.get("header", "Untitled")[:100],
                    value=str(i),
                    description=f"Page {i+1}"
                )
                for i, page in enumerate(pages)
            ]
        )
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, interaction: Interaction):
        """Handle page selection."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to remove pages.", ephemeral=True)
            return
        
        page_index = int(interaction.data["values"][0])
        page_header = self.pages[page_index].get("header", "Untitled")
        
        # Confirm removal
        confirm_view = ConfirmRemoveView(self.cog, self.message_id, page_index, page_header)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to remove page **{page_header}**? This cannot be undone.",
            view=confirm_view,
            ephemeral=True
        )


class ConfirmRemoveView(discord.ui.View):
    """View for confirming page removal."""
    
    def __init__(self, cog, message_id: int, page_index: int, page_header: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        self.page_index = page_index
        self.page_header = page_header
    
    @discord.ui.button(label="Confirm Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button):
        """Confirm removal."""
        if not interaction.guild:
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to remove pages.", ephemeral=True)
            return
        
        # Check if carousel still exists and has enough pages
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ Carousel no longer exists or has no pages.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        if self.page_index >= len(pages):
            await interaction.response.send_message("❌ Page index is invalid.", ephemeral=True)
            return
        
        if len(pages) == 1:
            await interaction.response.send_message("❌ Cannot remove the last page. Delete the carousel instead with `/lore remove`.", ephemeral=True)
            return
        
        # Remove the page
        success = self.cog.config.remove_page(self.message_id, self.page_index)
        
        if not success:
            await interaction.response.send_message("❌ Failed to remove page.", ephemeral=True)
            return
        
        # Update the carousel message if in standard mode
        await interaction.response.defer(ephemeral=True)
        carousel = self.cog.config.get_carousel(self.message_id)
        if carousel and not carousel.get("ephemeral_mode", False):
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                await self.cog.update_carousel_message(channel, message_id=self.message_id, page_index=0)
        
        await interaction.followup.send(f"✅ Removed page: **{self.page_header}**", ephemeral=True)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button):
        """Cancel removal."""
        await interaction.response.edit_message(content="❌ Page removal cancelled.", view=None)


class StartCarouselView(discord.ui.View):
    """View with a 'Start Here' button to launch the carousel privately."""
    
    def __init__(self, cog, message_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.message_id = message_id
        
        # Get custom button label from config
        carousel = cog.config.get_carousel(message_id)
        button_label = carousel.get("ephemeral_button_label", "Start Here") if carousel else "Start Here"
        
        # Add start button with unique custom_id
        button = discord.ui.Button(
            label=button_label,
            style=discord.ButtonStyle.primary,
            custom_id=f"start_carousel_{message_id}"
        )
        button.callback = self.start_carousel
        self.add_item(button)
        
        # Add admin button (visible to all but only functional for admins)
        admin_button = discord.ui.Button(
            label="⚙️ Admin",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ephemeral_admin_{message_id}"
        )
        admin_button.callback = self.on_admin_menu
        self.add_item(admin_button)
    
    async def on_admin_menu(self, interaction: Interaction):
        """Handle admin menu button click (admin only)."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to access the admin menu.", ephemeral=True)
            return
        
        # Get message_id - prefer from self, then from interaction message, then from custom_id
        message_id = None
        if hasattr(self, 'message_id') and self.message_id:
            message_id = self.message_id
        elif interaction.message:
            message_id = interaction.message.id
        else:
            # Fallback: try to extract from custom_id
            if hasattr(interaction, 'data') and interaction.data:
                custom_id = interaction.data.get('custom_id', '')
                if custom_id.startswith('ephemeral_admin_'):
                    try:
                        message_id = int(custom_id.replace('ephemeral_admin_', ''))
                    except ValueError:
                        pass
        
        if not message_id:
            await interaction.response.send_message("❌ Could not identify carousel.", ephemeral=True)
            return
        
        # Verify carousel exists
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel:
            await interaction.response.send_message(f"❌ Carousel not found. (message_id: {message_id})", ephemeral=True)
            return
        
        # Show admin menu with option to switch back to standard mode
        admin_view = EphemeralAdminView(self.cog, message_id)
        await interaction.response.send_message("**Admin Menu** - Select an action:", view=admin_view, ephemeral=True)
    
    async def start_carousel(self, interaction: Interaction):
        """Handle start button click - show carousel privately."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        # Get message_id - prefer from self (set during view creation), then from interaction message
        message_id = None
        if hasattr(self, 'message_id') and self.message_id:
            message_id = self.message_id
        elif interaction.message:
            message_id = interaction.message.id
        else:
            # Fallback: try to extract from custom_id
            if hasattr(interaction, 'data') and interaction.data:
                custom_id = interaction.data.get('custom_id', '')
                if custom_id.startswith('start_carousel_'):
                    try:
                        message_id = int(custom_id.replace('start_carousel_', ''))
                    except ValueError:
                        pass
        
        if not message_id:
            await interaction.response.send_message("❌ Could not identify carousel.", ephemeral=True)
            return
        
        # Try to get carousel by message_id
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message(f"❌ Carousel not found or has no pages. (message_id: {message_id})", ephemeral=True)
            return
        
        pages = carousel["pages"]
        page = pages[0]
        
        # Create embed for first page
        embed = discord.Embed(
            title=page.get("header", "Untitled"),
            description=page.get("body", ""),
            color=discord.Color.blue()
        )
        
        if page.get("image_url"):
            embed.set_image(url=page["image_url"])
        
        embed.set_footer(text=f"Page 1 of {len(pages)}")
        
        # Create ephemeral carousel view
        view = EphemeralCarouselView(self.cog, message_id, 0)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class EphemeralCarouselView(discord.ui.View):
    """View for ephemeral carousel navigation."""
    
    def __init__(self, cog, message_id: int, current_page: int = 0):
        super().__init__(timeout=300)  # 5 minute timeout for ephemeral
        self.cog = cog
        self.message_id = message_id
        self.current_page = current_page
        self._update_components()
    
    def _update_components(self):
        """Update the select menu and buttons with current pages."""
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            return
        
        pages = carousel["pages"]
        
        # Clear existing items
        self.clear_items()
        
        # Add select menu for page selection
        select = discord.ui.Select(
            placeholder="Select a page...",
            options=[
                discord.SelectOption(
                    label=page.get("header", "Untitled")[:100],
                    value=str(i),
                    description=page.get("body", "")[:100] if len(page.get("body", "")) <= 100 else page.get("body", "")[:97] + "..."
                )
                for i, page in enumerate(pages)
            ]
        )
        select.callback = self.on_select_page
        self.add_item(select)
        
        # Add navigation buttons
        prev_button = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary)
        prev_button.callback = self.on_prev
        self.add_item(prev_button)
        
        next_button = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)
        next_button.callback = self.on_next
        self.add_item(next_button)
    
    async def on_select_page(self, interaction: Interaction):
        """Handle page selection from dropdown."""
        if not interaction.guild:
            return
        
        page_index = int(interaction.data["values"][0])
        self.current_page = page_index
        
        await self._update_ephemeral_message(interaction, page_index)
    
    async def on_prev(self, interaction: Interaction):
        """Handle previous button click."""
        if not interaction.guild:
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        self.current_page = (self.current_page - 1) % len(pages)
        
        await self._update_ephemeral_message(interaction, self.current_page)
    
    async def on_next(self, interaction: Interaction):
        """Handle next button click."""
        if not interaction.guild:
            return
        
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        self.current_page = (self.current_page + 1) % len(pages)
        
        await self._update_ephemeral_message(interaction, self.current_page)
    
    async def _update_ephemeral_message(self, interaction: Interaction, page_index: int):
        """Update the ephemeral message with the selected page."""
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            return
        
        pages = carousel["pages"]
        if page_index >= len(pages):
            page_index = 0
        
        page = pages[page_index]
        
        # Create embed
        embed = discord.Embed(
            title=page.get("header", "Untitled"),
            description=page.get("body", ""),
            color=discord.Color.blue()
        )
        
        if page.get("image_url"):
            embed.set_image(url=page["image_url"])
        
        embed.set_footer(text=f"Page {page_index + 1} of {len(pages)}")
        
        # Update view with new page
        self.current_page = page_index
        self._update_components()
        
        # Edit the ephemeral message
        await interaction.response.edit_message(embed=embed, view=self)


class LoreCarouselView(discord.ui.View):
    """View for the lore carousel with select menu and navigation."""
    
    def __init__(self, cog, message_id: int, current_page: int = 0):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.message_id = message_id
        self.current_page = current_page
        self._update_select_menu()
    
    def _update_select_menu(self):
        """Update the select menu with current pages."""
        carousel = self.cog.config.get_carousel(self.message_id)
        if not carousel or not carousel.get("pages"):
            return
        
        pages = carousel["pages"]
        
        # Clear existing select menu
        self.clear_items()
        
        # Add select menu for page selection
        select = discord.ui.Select(
            placeholder="Select a page...",
            options=[
                discord.SelectOption(
                    label=page.get("header", "Untitled")[:100],
                    value=str(i),
                    description=page.get("body", "")[:100] if len(page.get("body", "")) <= 100 else page.get("body", "")[:97] + "..."
                )
                for i, page in enumerate(pages)
            ]
        )
        select.callback = self.on_select_page
        self.add_item(select)
        
        # Add navigation buttons
        prev_button = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id=f"carousel_prev_{self.message_id}")
        prev_button.callback = self.on_prev
        self.add_item(prev_button)
        
        next_button = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id=f"carousel_next_{self.message_id}")
        next_button.callback = self.on_next
        self.add_item(next_button)
        
        # Add admin menu button (visible to all but only functional for admins)
        admin_button = discord.ui.Button(label="⚙️ Admin Menu", style=discord.ButtonStyle.secondary, custom_id=f"carousel_admin_{self.message_id}")
        admin_button.callback = self.on_admin_menu
        self.add_item(admin_button)
    
    def _get_message_id(self, interaction: Interaction) -> Optional[int]:
        """Extract message_id from multiple sources."""
        # Try from self first
        if hasattr(self, 'message_id') and self.message_id:
            return self.message_id
        
        # Try from interaction message
        if interaction.message:
            return interaction.message.id
        
        # Try to extract from custom_id (for persistent views)
        if hasattr(interaction, 'data') and interaction.data:
            custom_id = interaction.data.get('custom_id', '')
            for prefix in ['carousel_prev_', 'carousel_next_', 'carousel_admin_']:
                if custom_id.startswith(prefix):
                    try:
                        return int(custom_id.replace(prefix, ''))
                    except ValueError:
                        pass
        
        return None
    
    async def on_select_page(self, interaction: Interaction):
        """Handle page selection from dropdown."""
        if not interaction.guild:
            return
        
        message_id = self._get_message_id(interaction)
        if not message_id:
            await interaction.response.send_message("❌ Could not identify carousel.", ephemeral=True)
            return
        
        page_index = int(interaction.data["values"][0])
        self.current_page = page_index
        
        await interaction.response.defer()
        carousel = self.cog.config.get_carousel(message_id)
        if carousel:
            channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
            if channel:
                await self.cog.update_carousel_message(channel, message_id=message_id, page_index=page_index)
    
    async def on_prev(self, interaction: Interaction):
        """Handle previous button click."""
        if not interaction.guild:
            return
        
        message_id = self._get_message_id(interaction)
        if not message_id:
            await interaction.response.send_message("❌ Could not identify carousel.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        self.current_page = (self.current_page - 1) % len(pages)
        
        await interaction.response.defer()
        channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
        if channel:
            await self.cog.update_carousel_message(channel, message_id=message_id, page_index=self.current_page)
    
    async def on_next(self, interaction: Interaction):
        """Handle next button click."""
        if not interaction.guild:
            return
        
        message_id = self._get_message_id(interaction)
        if not message_id:
            await interaction.response.send_message("❌ Could not identify carousel.", ephemeral=True)
            return
        
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel or not carousel.get("pages"):
            await interaction.response.send_message("❌ No pages available.", ephemeral=True)
            return
        
        pages = carousel["pages"]
        self.current_page = (self.current_page + 1) % len(pages)
        
        await interaction.response.defer()
        channel = get_channel_or_thread(interaction.guild, carousel["channel_id"])
        if channel:
            await self.cog.update_carousel_message(channel, message_id=message_id, page_index=self.current_page)
    
    async def on_admin_menu(self, interaction: Interaction):
        """Handle admin menu button click (admin only)."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to access the admin menu.", ephemeral=True)
            return
        
        message_id = self._get_message_id(interaction)
        if not message_id:
            await interaction.response.send_message("❌ Could not identify carousel. Please try again.", ephemeral=True)
            return
        
        # Verify carousel exists
        carousel = self.cog.config.get_carousel(message_id)
        if not carousel:
            await interaction.response.send_message("❌ Carousel not found. The carousel may have been deleted.", ephemeral=True)
            return
        
        # Show admin menu with select options
        admin_view = AdminMenuView(self.cog, message_id)
        await interaction.response.send_message("**Admin Menu** - Select an action:", view=admin_view, ephemeral=True)
    
    async def interaction_check(self, interaction: Interaction) -> bool:
        """Check if interaction is valid."""
        return interaction.guild is not None


class LoreCarousel(commands.Cog):
    """Lore carousel system with dropdown and pagination."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = LoreCarouselConfig()
        self.carousel_messages: Dict[int, int] = {}  # channel_id -> message_id
        self._load_carousel_messages()
    
    
    def _load_carousel_messages(self):
        """Load carousel message IDs from config on startup and restore persistent views."""
        data = self.config._load()
        restored_count = 0
        for key, carousel in data.get("carousels", {}).items():
            if "message_id" in carousel:
                # Store message_id -> channel_id mapping for quick lookup
                try:
                    message_id = int(key)
                    self.carousel_messages[message_id] = carousel["channel_id"]
                    
                    # Only restore views for carousels that have pages
                    if not carousel.get("pages"):
                        continue
                    
                    # Restore persistent view for this carousel
                    ephemeral_mode = carousel.get("ephemeral_mode", False)
                    if ephemeral_mode:
                        # Restore ephemeral mode view (Start Here button)
                        # This works because it only has a button with custom_id
                        view = StartCarouselView(self, message_id)
                        self.bot.add_view(view)
                        restored_count += 1
                    else:
                        # For standard mode, we can't use bot.add_view() because select menus
                        # don't have custom_ids. The view will be restored when the message
                        # is edited next, or users can use /lore restore to fix it immediately.
                        # We'll still try to register it, but catch the error if it fails.
                        try:
                            view = LoreCarouselView(self, message_id, 0)
                            self.bot.add_view(view)
                            restored_count += 1
                        except Exception:
                            # Select menu views can't be registered with bot.add_view()
                            # They'll work when the message is next edited, or use /lore restore
                            pass
                except (ValueError, TypeError) as e:
                    # Skip invalid message IDs
                    continue
                except Exception as e:
                    # Log but continue for other errors
                    import logging
                    logging.getLogger("bot").warning(f"Failed to restore carousel view for message_id {key}: {e}")
                    continue
        
        # Also restore selector views
        for key, selector in data.get("selectors", {}).items():
            if "message_id" in selector:
                try:
                    message_id = int(key)
                    # Restore selector view
                    view = CarouselSelectorView(self, message_id)
                    self.bot.add_view(view, message_id=message_id)
                    restored_count += 1
                except (ValueError, TypeError):
                    continue
                except Exception as e:
                    import logging
                    logging.getLogger("bot").warning(f"Failed to restore selector view for message_id {key}: {e}")
                    continue
        
        if restored_count > 0:
            import logging
            logging.getLogger("bot").info(f"Restored {restored_count} persistent carousel view(s) on startup")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Update existing ephemeral carousels to include admin button."""
        # Migrate guild_ids retroactively first
        self.config.migrate_add_guild_ids(self.bot)
        
        # Wait a bit for everything to be ready
        await asyncio.sleep(2)
        
        import logging
        log = logging.getLogger("bot")
        updated_count = 0
        
        data = self.config._load()
        for key, carousel in data.get("carousels", {}).items():
            if not carousel.get("ephemeral_mode", False):
                continue
            
            if not carousel.get("pages"):
                continue
            
            try:
                message_id = int(key)
                channel_id = carousel.get("channel_id")
                if not channel_id:
                    continue
                
                guild = None
                for g in self.bot.guilds:
                    if get_channel_or_thread(g, channel_id):
                        guild = g
                        break
                
                if not guild:
                    continue
                
                channel = get_channel_or_thread(guild, channel_id)
                if not channel:
                    continue
                
                try:
                    message = await channel.fetch_message(message_id)
                    # Check if message already has admin button (has 2 buttons)
                    if message.components and len(message.components) > 0:
                        total_buttons = sum(1 for row in message.components for item in row.children if isinstance(item, discord.ui.Button))
                        if total_buttons >= 2:
                            # Already has admin button, skip
                            continue
                    
                    # Update message with new view that includes admin button
                    title = carousel.get("ephemeral_title", "📚 Lore Carousel")
                    description = carousel.get("ephemeral_description", "Click the button below to start exploring!")
                    start_embed = discord.Embed(
                        title=title,
                        description=description,
                        color=discord.Color.blue()
                    )
                    image_url = carousel.get("ephemeral_image_url")
                    if image_url:
                        start_embed.set_image(url=image_url)
                    start_view = StartCarouselView(self, message_id)
                    self.bot.add_view(start_view)
                    await message.edit(embed=start_embed, view=start_view)
                    updated_count += 1
                    await asyncio.sleep(0.5)  # Rate limit protection
                except discord.NotFound:
                    # Message was deleted, skip
                    continue
                except Exception as e:
                    log.warning(f"Failed to update ephemeral carousel {message_id}: {e}")
                    continue
            except (ValueError, TypeError):
                continue
            except Exception as e:
                log.warning(f"Error processing carousel {key}: {e}")
                continue
        
        if updated_count > 0:
            log.info(f"Updated {updated_count} existing ephemeral carousel(s) with admin button")
    
    async def update_carousel_message(self, channel: discord.abc.Messageable, message_id: Optional[int] = None, page_index: int = 0):
        """Update the carousel message with the current page. Works with both channels and threads."""
        if not channel:
            return
        
        # If message_id not provided, try to find existing carousel in channel (backward compat)
        if not message_id:
            carousel_data = self.config.get_carousel_by_channel(channel.id)
            if carousel_data and carousel_data.get("message_id"):
                message_id = carousel_data["message_id"]
            else:
                # No existing carousel, can't update
                return
        
        carousel = self.config.get_carousel(message_id)
        if not carousel or not carousel.get("pages"):
            return
        
        # Check if carousel is in ephemeral mode - if so, don't update the message
        if carousel.get("ephemeral_mode", False):
            return
        
        pages = carousel["pages"]
        if page_index >= len(pages):
            page_index = 0
        
        page = pages[page_index]
        
        # Create embed
        embed = discord.Embed(
            title=page.get("header", "Untitled"),
            description=page.get("body", ""),
            color=discord.Color.blue()
        )
        
        if page.get("image_url"):
            embed.set_image(url=page["image_url"])
        
        embed.set_footer(text=f"Page {page_index + 1} of {len(pages)}")
        
        # Create/update view
        view = LoreCarouselView(self, message_id, page_index)
        # Note: We don't call bot.add_view() here because views with select menus
        # can't be registered that way. Editing the message makes the view persistent.
        
        # Update or create message
        try:
            message = await channel.fetch_message(message_id)
            # Only edit if the message was authored by the bot
            if message.author.id == self.bot.user.id:
                await message.edit(embed=embed, view=view)
                return
            else:
                # Message exists but wasn't created by bot, create new one
                pass
        except discord.NotFound:
            # Message was deleted, create new one
            pass
        except discord.Forbidden:
            # Can't edit this message (not authored by bot), create new one
            pass
        
        # Create new message
        message = await channel.send(embed=embed, view=view)
        # Update carousel with new message_id
        guild_id = channel.guild.id if channel.guild else None
        self.config.add_carousel(channel.id, carousel["pages"], message.id, ephemeral_mode=False, guild_id=guild_id)
        self.carousel_messages[message.id] = channel.id
    
    lore_group = app_commands.Group(name="lore", description="Lore carousel commands")
    
    @lore_group.command(name="create", description="Create a new lore carousel in this channel")
    @app_commands.describe(
        initial_header="Initial page header",
        initial_body="Initial page body content",
        image_url="Optional image URL for the initial page (or use attachment parameter)",
        attachment="Optional image attachment (alternative to image_url)"
    )
    @app_commands.default_permissions(administrator=True)
    async def lore_create(
        self,
        interaction: Interaction,
        initial_header: str,
        initial_body: str,
        image_url: Optional[str] = None,
        attachment: Optional[discord.Attachment] = None
    ):
        """Create a new lore carousel in the current channel."""
        # Do quick checks first, then defer
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to create carousels.", ephemeral=True)
            return
        
        # Defer after quick checks to allow async work
        # This must happen within 3 seconds of the interaction
        await interaction.response.defer(ephemeral=True)
        
        # Handle image - prefer attachment over URL
        final_image_url = None
        if attachment:
            # Check if attachment is an image
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                await interaction.followup.send("❌ Attachment must be an image.", ephemeral=True)
                return
            final_image_url = attachment.url
        elif image_url:
            # Validate image URL if provided
            if not (image_url.startswith("http://") or image_url.startswith("https://")):
                await interaction.followup.send("❌ Image URL must be a valid HTTP/HTTPS URL.", ephemeral=True)
                return
            final_image_url = image_url
        
        # Validate body length (Discord embed limit is 4096)
        if len(initial_body) > 4096:
            await interaction.followup.send("❌ Body content cannot exceed 4096 characters.", ephemeral=True)
            return
        
        try:
            # Check if we're in a thread and if it's accessible
            channel = interaction.channel
            if isinstance(channel, discord.Thread):
                # Check if thread is archived or locked
                if channel.archived:
                    await interaction.followup.send("❌ Cannot create carousel in an archived thread. Please unarchive the thread first.", ephemeral=True)
                    return
                if channel.locked:
                    await interaction.followup.send("❌ Cannot create carousel in a locked thread. Please unlock the thread first.", ephemeral=True)
                    return
                
                # Check if bot has permission to send messages in this thread
                if not channel.permissions_for(interaction.guild.me).send_messages:
                    await interaction.followup.send("❌ I don't have permission to send messages in this thread. Please check the bot's permissions.", ephemeral=True)
                    return
            
            # Check permissions for regular channels too
            if hasattr(channel, 'permissions_for'):
                perms = channel.permissions_for(interaction.guild.me)
                if not perms.send_messages:
                    await interaction.followup.send("❌ I don't have permission to send messages in this channel. Please check the bot's permissions.", ephemeral=True)
                    return
            
            # Create embed for initial page (standard mode by default)
            embed = discord.Embed(
                title=initial_header,
                description=initial_body,
                color=discord.Color.blue()
            )
            
            if final_image_url:
                embed.set_image(url=final_image_url)
            
            embed.set_footer(text="Page 1 of 1")
            
            # Create the carousel message first (standard mode)
            # interaction.channel works for both regular channels and threads
            message = await channel.send(embed=embed)
            
            # Now create carousel with the message_id (ephemeral_mode=False by default)
            self.config.add_carousel(channel.id, [{
                "header": initial_header,
                "body": initial_body,
                "image_url": final_image_url
            }], message.id, ephemeral_mode=False, guild_id=interaction.guild.id if interaction.guild else None)
            
            # Update message with view
            view = LoreCarouselView(self, message.id, 0)
            # Note: We don't call bot.add_view() here because views with select menus
            # can't be registered that way. Editing the message makes the view persistent.
            await message.edit(view=view)
            
            self.carousel_messages[message.id] = channel.id
            
            await interaction.followup.send("✅ Lore carousel created! Use the admin menu to toggle ephemeral mode if desired.", ephemeral=True)
        except discord.Forbidden as e:
            # Handle permission errors specifically
            error_msg = "❌ I don't have permission to create a carousel here. Please check that I have permission to send messages and embed links in this channel/thread."
            print(f"[lore_carousel] Permission error in lore_create: {e}")
            try:
                await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as followup_error:
                print(f"[lore_carousel] Failed to send followup error: {followup_error}")
        except Exception as e:
            # Make sure we send an error message if something goes wrong
            import traceback
            error_msg = f"❌ Error creating carousel: {str(e)}"
            print(f"[lore_carousel] Error in lore_create: {e}")
            print(traceback.format_exc())
            try:
                await interaction.followup.send(error_msg, ephemeral=True)
            except Exception as followup_error:
                # If followup fails, log it but don't raise - we already deferred
                print(f"[lore_carousel] Failed to send followup error: {followup_error}")
    
    @lore_group.command(name="add", description="Add a page to the carousel in this channel")
    @app_commands.describe(
        header="Page header",
        body="Page body content",
        image_url="Optional image URL (or use attachment parameter)",
        attachment="Optional image attachment (alternative to image_url)"
    )
    @app_commands.default_permissions(administrator=True)
    async def lore_add(
        self,
        interaction: Interaction,
        header: str,
        body: str,
        image_url: Optional[str] = None,
        attachment: Optional[discord.Attachment] = None
    ):
        """Add a page to the carousel."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to add pages.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Handle image - prefer attachment over URL
        final_image_url = None
        if attachment:
            # Check if attachment is an image
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                await interaction.followup.send("❌ Attachment must be an image.", ephemeral=True)
                return
            final_image_url = attachment.url
        elif image_url:
            # Validate image URL if provided
            if not (image_url.startswith("http://") or image_url.startswith("https://")):
                await interaction.followup.send("❌ Image URL must be a valid HTTP/HTTPS URL.", ephemeral=True)
                return
            final_image_url = image_url
        
        # Validate body length (Discord embed limit is 4096)
        if len(body) > 4096:
            await interaction.followup.send("❌ Body content cannot exceed 4096 characters.", ephemeral=True)
            return
        
        # Check if carousel exists (get most recent in channel)
        carousel = self.config.get_carousel_by_channel(interaction.channel.id)
        if not carousel or not carousel.get("message_id"):
            await interaction.followup.send("❌ No carousel found in this channel. Use `/lore create` first.", ephemeral=True)
            return
        
        message_id = carousel["message_id"]
        
        # Verify carousel exists with this message_id
        carousel = self.config.get_carousel(message_id)
        if not carousel:
            await interaction.followup.send("❌ Carousel not found. The carousel may have been deleted. Please create a new one with `/lore create`.", ephemeral=True)
            return
        
        # Add page
        page_index = self.config.add_page(message_id, header, body, final_image_url)
        
        # Note: We don't need to update the "Start Here" button message
        # The ephemeral view will automatically pick up the new page when users interact
        
        await interaction.followup.send(f"✅ Added page: **{header}**", ephemeral=True)
    
    @lore_group.command(name="restore", description="Restore/re-register all carousel views in this server (fixes broken buttons)")
    @app_commands.default_permissions(administrator=True)
    async def lore_restore(self, interaction: Interaction):
        """Restore all carousel views in the server - useful if buttons stopped working after a bot restart."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Find all carousels in this server (guild)
        guild_id = interaction.guild.id
        carousels_in_server = []
        
        # Get all carousels for this guild
        data = self.config._load()
        for key, carousel in data.get("carousels", {}).items():
            # Get message_id - prefer from carousel data, fallback to key
            message_id = carousel.get("message_id")
            if not message_id:
                try:
                    message_id = int(key)
                except (ValueError, TypeError):
                    continue
            else:
                try:
                    message_id = int(message_id)
                except (ValueError, TypeError):
                    continue
            
            # Check if this carousel belongs to this guild
            carousel_guild_id = carousel.get("guild_id")
            channel_id = carousel.get("channel_id")
            
            # Check if guild_id matches
            if carousel_guild_id == guild_id:
                # Only include if it has pages
                if carousel.get("pages"):
                    carousels_in_server.append((message_id, carousel))
            elif carousel_guild_id is None and channel_id:
                # Fallback: check if channel belongs to this guild (for unmigrated carousels)
                try:
                    channel = get_channel_or_thread(interaction.guild, int(channel_id))
                    if channel:
                        # Only include if it has pages
                        if carousel.get("pages"):
                            carousels_in_server.append((message_id, carousel))
                except:
                    pass
        
        if not carousels_in_server:
            await interaction.followup.send(f"❌ No carousels found in this server.", ephemeral=True)
            return
        
        # Restore all carousels
        restored_count = 0
        failed_count = 0
        results = []
        
        for message_id, carousel in carousels_in_server:
            try:
                ephemeral_mode = carousel.get("ephemeral_mode", False)
                channel_id = carousel.get("channel_id")
                channel = get_channel_or_thread(interaction.guild, channel_id) if channel_id else None
                if not channel:
                    failed_count += 1
                    results.append(f"❌ Carousel {message_id}: Channel not found (channel_id: {channel_id})")
                    continue
                
                # Try to fetch the message - use message_id from carousel data first, then fallback to the key
                carousel_message_id = carousel.get("message_id") or message_id
                try:
                    message = await channel.fetch_message(carousel_message_id)
                except discord.NotFound:
                    # Try with the key as message_id (in case the message_id field is wrong)
                    try:
                        message = await channel.fetch_message(message_id)
                    except discord.NotFound:
                        failed_count += 1
                        results.append(f"❌ Carousel {message_id}: Message not found (tried {carousel_message_id} and {message_id})")
                        continue
                
                # Use the actual message ID from the fetched message
                actual_message_id = message.id
                
                # Always update the carousel key in JSON to match actual message_id (fixes mismatched keys)
                data = self.config._load()
                old_key = str(message_id)
                new_key = str(actual_message_id)
                
                # If the key doesn't match, update it
                if old_key != new_key or old_key not in data["carousels"]:
                    # Find the carousel data (might be under old_key or we need to search)
                    carousel_data = None
                    if old_key in data["carousels"]:
                        carousel_data = data["carousels"][old_key]
                    else:
                        # Search for it by message_id
                        for key, data_item in data["carousels"].items():
                            if data_item.get("message_id") == actual_message_id:
                                carousel_data = data_item
                                old_key = key
                                break
                    
                    if carousel_data:
                        carousel_data["message_id"] = actual_message_id
                        data["carousels"][new_key] = carousel_data
                        if old_key != new_key:
                            data["carousels"].pop(old_key, None)
                        self.config._save(data)
                        # Update carousel reference
                        carousel = data["carousels"].get(new_key, carousel)
                
                if ephemeral_mode:
                    # Restore ephemeral mode view with custom text
                    title = carousel.get("ephemeral_title", "📚 Lore Carousel")
                    description = carousel.get("ephemeral_description", "Click the button below to start exploring!")
                    start_embed = discord.Embed(
                        title=title,
                        description=description,
                        color=discord.Color.blue()
                    )
                    image_url = carousel.get("ephemeral_image_url")
                    if image_url:
                        start_embed.set_image(url=image_url)
                    view = StartCarouselView(self, actual_message_id)
                    # Register the view (button has custom_id, so this works)
                    self.bot.add_view(view)
                    # Update the message to re-attach the view
                    await message.edit(embed=start_embed, view=view)
                    restored_count += 1
                    results.append(f"✅ Ephemeral carousel {actual_message_id} in #{channel.name}: Restored")
                else:
                    # Restore standard mode view - update the message (this makes it persistent)
                    await self.update_carousel_message(channel, message_id=actual_message_id)
                    restored_count += 1
                    results.append(f"✅ Standard carousel {actual_message_id} in #{channel.name}: Restored")
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
            except Exception as e:
                failed_count += 1
                results.append(f"❌ Carousel {message_id}: {str(e)[:100]}")
                continue
        
        # Send summary
        summary = f"**Restore Complete**\n\n"
        summary += f"✅ Restored: {restored_count}\n"
        if failed_count > 0:
            summary += f"❌ Failed: {failed_count}\n"
        summary += f"\n**Details:**\n" + "\n".join(results[:20])  # Limit to first 20 results
        
        if len(results) > 20:
            summary += f"\n... and {len(results) - 20} more"
        
        await interaction.followup.send(summary, ephemeral=True)
    
    @lore_group.command(name="remove", description="Remove a lore carousel from the server")
    @app_commands.default_permissions(administrator=True)
    async def lore_remove(self, interaction: Interaction):
        """Remove a carousel from the server (with dropdown selection and confirmation)."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to remove carousels.", ephemeral=True)
            return
        
        # Get all carousels from the server
        carousels = self.config.get_carousels_by_guild(interaction.guild.id, bot=self.bot, ephemeral_only=False)
        
        if not carousels:
            await interaction.response.send_message("❌ No carousels found in this server.", ephemeral=True)
            return
        
        # Show dropdown to select which carousel to delete
        view = SelectCarouselToDeleteView(self, carousels)
        await interaction.response.send_message("**Remove Carousel**\n\nSelect a carousel to remove:", view=view, ephemeral=True)
    
    @lore_group.command(name="repost", description="Repost a carousel to a different channel or thread")
    @app_commands.describe(
        channel="The channel or thread to repost the carousel to"
    )
    @app_commands.default_permissions(administrator=True)
    async def lore_repost(self, interaction: Interaction, channel: Union[discord.TextChannel, discord.Thread]):
        """Repost a carousel to a different channel with dropdown selection."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to repost carousels.", ephemeral=True)
            return
        
        # Check if target channel is a thread and if it's accessible
        if isinstance(channel, discord.Thread):
            if channel.archived:
                await interaction.response.send_message("❌ Cannot repost carousel to an archived thread. Please unarchive the thread first.", ephemeral=True)
                return
            if channel.locked:
                await interaction.response.send_message("❌ Cannot repost carousel to a locked thread. Please unlock the thread first.", ephemeral=True)
                return
        
        # Check if bot has permission to send messages in the target channel
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message("❌ I don't have permission to send messages in that channel. Please check the bot's permissions.", ephemeral=True)
            return
        
        if not channel.permissions_for(interaction.guild.me).embed_links:
            await interaction.response.send_message("❌ I don't have permission to embed links in that channel. Please check the bot's permissions.", ephemeral=True)
            return
        
        # Try to migrate guild_ids first (in case some carousels don't have it set)
        self.config.migrate_add_guild_ids(self.bot)
        
        # Get all carousels from the server
        carousels = self.config.get_carousels_by_guild(interaction.guild.id, bot=self.bot, ephemeral_only=False)
        
        if not carousels:
            # Try to get all carousels without guild filter as a fallback
            data = self.config._load()
            all_carousels = []
            for carousel_data in data.get("carousels", {}).values():
                if carousel_data.get("pages"):
                    # Check if channel exists in this guild
                    channel_id = carousel_data.get("channel_id")
                    if channel_id:
                        ch = get_channel_or_thread(interaction.guild, channel_id)
                        if ch:
                            all_carousels.append(carousel_data)
            
            if all_carousels:
                carousels = all_carousels
            else:
                await interaction.response.send_message(
                    "❌ No carousels found in this server.\n\n"
                    "**Tip:** Make sure carousels have been created in this server, or that their channels still exist.",
                    ephemeral=True
                )
                return
        
        # Show view with carousel dropdown
        view = RepostCarouselView(self, channel, carousels)
        await interaction.response.send_message(
            f"**Repost Carousel**\n\nSelect a carousel to repost to {channel.mention}:",
            view=view,
            ephemeral=True
        )
    
    # Selector commands - create as a separate group
    selector_group = app_commands.Group(
        name="selector",
        description="Manage carousel selectors (button bars with multiple carousels)",
        parent=lore_group
    )
    
    @selector_group.command(name="create", description="Create a carousel selector (button bar for multiple ephemeral carousels)")
    @app_commands.describe(
        title="Title for the selector embed",
        description="Description for the selector embed",
        image_url="Optional image URL for the selector embed",
        attachment="Optional image attachment (alternative to image_url)"
    )
    @app_commands.default_permissions(administrator=True)
    async def selector_create(self, interaction: Interaction, title: str = "📚 Lore Carousels", description: str = "Select a carousel to explore:", image_url: Optional[str] = None, attachment: Optional[discord.Attachment] = None):
        """Create a new carousel selector."""
        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to create selectors.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Handle image - prefer attachment over URL
        final_image_url = None
        if attachment:
            # Check if attachment is an image
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                await interaction.followup.send("❌ Attachment must be an image.", ephemeral=True)
                return
            final_image_url = attachment.url
        elif image_url:
            # Validate image URL if provided
            if not (image_url.startswith("http://") or image_url.startswith("https://")):
                await interaction.followup.send("❌ Image URL must be a valid HTTP/HTTPS URL.", ephemeral=True)
                return
            final_image_url = image_url
        
        # Create embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=0x5865F2
        )
        if final_image_url:
            embed.set_image(url=final_image_url)
        embed.set_footer(text="Add carousels to this selector using the ⚙️ Admin button")
        
        # Send message first (without view, since we need the message_id)
        message = await interaction.channel.send(embed=embed)
        
        # Save selector with actual message_id
        self.config.add_selector(interaction.channel.id, message.id, title, description, guild_id=interaction.guild.id if interaction.guild else None, image_url=final_image_url)
        
        # Create view with correct message_id
        view = CarouselSelectorView(self, message.id)
        await message.edit(embed=embed, view=view)
        
        # Register the view
        self.bot.add_view(view, message_id=message.id)
        
        await interaction.followup.send(f"✅ Carousel selector created! Message ID: {message.id}\n\nUse the ⚙️ Admin button on the selector to add carousels.", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = LoreCarousel(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(cog.lore_group)
    except app_commands.CommandAlreadyRegistered:
        pass

