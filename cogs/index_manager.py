# cogs/index_manager.py

import json
import os
import asyncio
import re
import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, List, Set, Union
from rapidfuzz import fuzz, process
from core.utils import rate_limit_retry, rate_limited_archived_threads, rate_limited_message_history

# Configuration file path
CONFIG_FILE = "data/index_config.json"

# Default index thread names to exclude
DEFAULT_EXCLUDE_NAMES = {"index", "📜 Character Index", "📚 Encyclopedia Index", "📂 Resources Index"}

class IndexConfig:
    """Manages index configurations stored in JSON."""
    
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
                json.dump({"indexes": {}, "character_forums": {}, "group_indexes": {}}, f, indent=2)
    
    def _load(self) -> dict:
        """Load configuration from file."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure required keys exist
                if "indexes" not in data:
                    data["indexes"] = {}
                if "character_forums" not in data:
                    data["character_forums"] = {}
                if "group_indexes" not in data:
                    data["group_indexes"] = {}
                return data
        except Exception:
            return {"indexes": {}, "character_forums": {}, "group_indexes": {}}
    
    def _save(self, data: dict):
        """Save configuration to file."""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def add_index(self, guild_id: int, forum_id: int, index_name: str, 
                  sort_by_tags: bool = False, preferred_tags: Optional[List[str]] = None,
                  index_thread_name: Optional[str] = None, intro_text: Optional[str] = None,
                  thumb_url: Optional[str] = None, use_character_sorting: bool = False,
                  priority_tag: Optional[str] = None, sort_by_title_pattern: bool = False,
                  title_grouping_pattern: Optional[str] = None):
        """Add or update an index configuration."""
        data = self._load()
        key = f"{guild_id}:{forum_id}"
        
        data["indexes"][key] = {
            "guild_id": guild_id,
            "forum_id": forum_id,
            "index_name": index_name,
            "sort_by_tags": sort_by_tags,
            "preferred_tags": preferred_tags or [],
            "index_thread_name": index_thread_name or f"📜 {index_name} Index",
            "intro_text": intro_text or f"📚 Index of {index_name}",
            "thumb_url": thumb_url,
            "use_character_sorting": use_character_sorting,
            "priority_tag": priority_tag,
            "sort_by_title_pattern": sort_by_title_pattern,
            "title_grouping_pattern": title_grouping_pattern
        }
        self._save(data)
    
    def remove_index(self, guild_id: int, forum_id: int):
        """Remove an index configuration."""
        data = self._load()
        key = f"{guild_id}:{forum_id}"
        data["indexes"].pop(key, None)
        self._save(data)
    
    def get_indexes(self, guild_id: Optional[int] = None) -> Dict[str, dict]:
        """Get all indexes, optionally filtered by guild_id."""
        data = self._load()
        indexes = data.get("indexes", {})
        if guild_id:
            return {k: v for k, v in indexes.items() if v.get("guild_id") == guild_id}
        return indexes
    
    def get_index(self, guild_id: int, forum_id: int) -> Optional[dict]:
        """Get a specific index configuration."""
        data = self._load()
        key = f"{guild_id}:{forum_id}"
        return data.get("indexes", {}).get(key)
    
    def add_character_forum(self, guild_id: int, forum_id: int):
        """Add a character forum for a guild."""
        data = self._load()
        if "character_forums" not in data:
            data["character_forums"] = {}
        
        guild_key = str(guild_id)
        if guild_key not in data["character_forums"]:
            data["character_forums"][guild_key] = []
        
        # Handle legacy format: if it's an integer, convert to list
        forums = data["character_forums"][guild_key]
        if isinstance(forums, int):
            data["character_forums"][guild_key] = [forums]
            forums = data["character_forums"][guild_key]
        
        # Ensure it's a list
        if not isinstance(forums, list):
            data["character_forums"][guild_key] = []
            forums = data["character_forums"][guild_key]
        
        # Add forum if not already in list
        if forum_id not in forums:
            forums.append(forum_id)
            self._save(data)
            return True
        return False
    
    def remove_character_forum(self, guild_id: int, forum_id: int):
        """Remove a character forum for a guild."""
        data = self._load()
        if "character_forums" not in data:
            return False
        
        guild_key = str(guild_id)
        if guild_key not in data["character_forums"]:
            return False
        
        forums = data["character_forums"][guild_key]
        
        # Handle legacy format: if it's an integer, convert to list first
        if isinstance(forums, int):
            if forums == forum_id:
                # If it's the only forum, remove the entry
                del data["character_forums"][guild_key]
                self._save(data)
                return True
            else:
                # Convert to list with the existing forum
                data["character_forums"][guild_key] = [forums]
                forums = data["character_forums"][guild_key]
        
        # Ensure it's a list
        if not isinstance(forums, list):
            return False
        
        if forum_id in forums:
            forums.remove(forum_id)
            # Remove empty lists
            if not forums:
                del data["character_forums"][guild_key]
            self._save(data)
            return True
        return False
    
    def get_character_forums(self, guild_id: int) -> List[int]:
        """Get all character forum IDs for a guild."""
        data = self._load()
        forums = data.get("character_forums", {}).get(str(guild_id), [])
        # Handle legacy single forum_id format (migrate on read)
        if isinstance(forums, int):
            return [forums]
        return forums if isinstance(forums, list) else []
    
    def set_character_forum(self, guild_id: int, forum_id: int):
        """Set a single character forum (legacy method, adds to list)."""
        self.add_character_forum(guild_id, forum_id)
    
    def add_group_index(self, guild_id: int, target_channel_id: int, group_index_name: str,
                       source_forum_ids: List[int], sort_by_tags: bool = False,
                       preferred_tags: Optional[List[str]] = None, intro_text: Optional[str] = None,
                       thumb_url: Optional[str] = None, use_character_sorting: bool = False,
                       priority_tag: Optional[str] = None, sort_by_title_pattern: bool = False,
                       title_grouping_pattern: Optional[str] = None, thread_sort_by: str = "creation",
                       thread_sort_tag: Optional[str] = None):
        """Add or update a group index configuration."""
        data = self._load()
        key = f"{guild_id}:{target_channel_id}"
        
        if "group_indexes" not in data:
            data["group_indexes"] = {}
        
        data["group_indexes"][key] = {
            "guild_id": guild_id,
            "target_channel_id": target_channel_id,
            "group_index_name": group_index_name,
            "source_forum_ids": source_forum_ids,
            "sort_by_tags": sort_by_tags,
            "preferred_tags": preferred_tags or [],
            "intro_text": intro_text or f"📚 Group Index: {group_index_name}",
            "thumb_url": thumb_url,
            "use_character_sorting": use_character_sorting,
            "priority_tag": priority_tag,
            "sort_by_title_pattern": sort_by_title_pattern,
            "title_grouping_pattern": title_grouping_pattern,
            "thread_sort_by": thread_sort_by,  # "creation" or "tag"
            "thread_sort_tag": thread_sort_tag  # Tag name if thread_sort_by is "tag"
        }
        self._save(data)
    
    def get_group_index(self, guild_id: int, target_channel_id: int) -> Optional[dict]:
        """Get a specific group index configuration."""
        data = self._load()
        key = f"{guild_id}:{target_channel_id}"
        return data.get("group_indexes", {}).get(key)
    
    def get_group_indexes(self, guild_id: Optional[int] = None) -> Dict[str, dict]:
        """Get all group indexes, optionally filtered by guild_id."""
        data = self._load()
        group_indexes = data.get("group_indexes", {})
        if guild_id:
            return {k: v for k, v in group_indexes.items() if v.get("guild_id") == guild_id}
        return group_indexes
    
    def remove_group_index(self, guild_id: int, target_channel_id: int):
        """Remove a group index configuration."""
        data = self._load()
        key = f"{guild_id}:{target_channel_id}"
        if "group_indexes" in data:
            data["group_indexes"].pop(key, None)
        self._save(data)


class IndexManager(commands.Cog):
    """Global index management system that works across multiple guilds."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = IndexConfig()
        self.index_thread_ids: Dict[str, int] = {}  # Cache of index thread IDs
        self.last_chunks: Dict[str, List[str]] = {}  # Cache of last chunks per index
        self.group_index_thread_ids: Dict[str, Dict[str, int]] = {}  # Cache of group index thread IDs: {key: {entry_name: thread_id}}
        self._startup_delay = 0  # Will be set based on cog load order
        self.update_index_task.start()
        self.update_group_index_task.start()
    
    def cog_unload(self):
        self.update_index_task.cancel()
        self.update_group_index_task.cancel()
    
    def _get_index_key(self, guild_id: int, forum_id: int) -> str:
        """Get the key for an index."""
        return f"{guild_id}:{forum_id}"
    
    def _extract_title_group_key(self, title: str, pattern: str) -> Optional[str]:
        """Extract grouping key from thread title using pattern.
        
        Supports:
        - Built-in patterns:
          - "after-" extracts everything after last dash
          - "before-" extracts before first dash  
          - "date-suffix" extracts date pattern like "SD1-582" or "WD1-582" anywhere in title
        - Regex pattern with capture group: r".*-(\d+)" captures suffix number
        - Regex pattern to match anywhere: r"([A-Z]+\d+-\d+)" captures date patterns like "SD1-582"
        """
        if not pattern:
            return None
        
        pattern_lower = pattern.lower()
        
        # Try simple built-in patterns first
        if pattern_lower == "after-":
            # Extract everything after the last dash
            if "-" in title:
                return title.rsplit("-", 1)[-1].strip()
            return None
        elif pattern_lower == "before-":
            # Extract everything before the first dash
            if "-" in title:
                return title.split("-", 1)[0].strip()
            return None
        elif pattern_lower == "date-suffix":
            # Extract date pattern like "SD1-582" or "WD1-582" anywhere in the title
            # Pattern: 2-4 letters, digits, dash, digits (matches "SD1-582", "WD2-582", etc.)
            date_match = re.search(r'([A-Z]{2,4}\d+-\d+)', title, re.IGNORECASE)
            if date_match:
                return date_match.group(1).upper()  # Normalize to uppercase
            return None
        elif pattern_lower == "date-number":
            # Extract just the date number (suffix after dash) from patterns like "SD1-582" or "WD2-582"
            # This groups threads by the in-world date number (582), ignoring the day prefix (WD1, SD1, etc.)
            # Pattern: finds date pattern and extracts the number after the dash
            date_match = re.search(r'[A-Z]{2,4}\d+-(\d+)', title, re.IGNORECASE)
            if date_match:
                return date_match.group(1)  # Just the number after dash (e.g., "582")
            # Fallback: try to find pattern like "-582" at end of title
            dash_match = re.search(r'-(\d+)(?:\s|$)', title)
            if dash_match:
                return dash_match.group(1)
            return None
        
        # Try regex pattern (matches anywhere in title by default)
        try:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                # Use first capture group if available, otherwise use full match
                if match.groups():
                    return match.group(1)
                return match.group(0)
        except re.error:
            # Invalid regex, pattern doesn't match
            pass
        
        return None
    
    async def build_index_text(self, forum: discord.ForumChannel, config: dict) -> List[str]:
        """Build index text based on configuration."""
        index_thread_name = config.get("index_thread_name", "Index")
        sort_by_tags = config.get("sort_by_tags", False)
        sort_by_title_pattern = config.get("sort_by_title_pattern", False)
        title_grouping_pattern = config.get("title_grouping_pattern")
        preferred_tags = config.get("preferred_tags", [])
        use_character_sorting = config.get("use_character_sorting", False)
        priority_tag = config.get("priority_tag")
        
        # Collect threads (active + archived), excluding index thread
        active_threads = list(forum.threads)
        # Use rate-limited archived threads fetching with delays
        archived_threads = await rate_limited_archived_threads(forum, limit=None, delay_between_pages=0.5)
        
        all_threads = active_threads + archived_threads
        
        # Filter out index threads and threads matching exclude names
        threads = [
            t for t in all_threads
            if t.name.lower() not in [name.lower() for name in DEFAULT_EXCLUDE_NAMES]
            and (not self.index_thread_ids.get(self._get_index_key(forum.guild.id, forum.id)) 
                 or t.id != self.index_thread_ids.get(self._get_index_key(forum.guild.id, forum.id)))
        ]
        
        if not threads:
            return ["No entries found."]
        
        # Use special character index sorting if enabled
        if use_character_sorting:
            return await self._build_character_index_text(forum, threads, preferred_tags, priority_tag)
        
        # Sort by title pattern if enabled
        if sort_by_title_pattern and title_grouping_pattern:
            return await self._build_title_pattern_index_text(forum, threads, title_grouping_pattern, priority_tag)
        
        if sort_by_tags:
            # Group by tags
            grouped = {}
            for thread in threads:
                tag_names = [tag.name for tag in thread.applied_tags]
                
                # If preferred tags are specified, only use those
                if preferred_tags:
                    matching_tags = [tag for tag in tag_names if tag.lower() in [pt.lower() for pt in preferred_tags]]
                    if matching_tags:
                        # Use the first matching preferred tag
                        tag = matching_tags[0]
                    else:
                        # If no preferred tag matches, use "Other"
                        tag = "Other"
                else:
                    # Use all tags, or "Other" if no tags
                    tag = tag_names[0] if tag_names else "Other"
                
                grouped.setdefault(tag, []).append(thread)
            
            # Build output lines grouped by tag
            lines = []
            
            # Get tag emojis from forum tags
            tag_emoji_map = {}
            if forum.available_tags:
                for tag_obj in forum.available_tags:
                    emoji_str = None
                    if tag_obj.emoji:
                        if isinstance(tag_obj.emoji, str):
                            emoji_str = tag_obj.emoji
                        else:
                            # Emoji object - convert to string
                            emoji_str = str(tag_obj.emoji)
                    tag_emoji_map[tag_obj.name.lower()] = emoji_str
            
            # Get priority tag emoji if priority tag is set
            priority_tag_emoji = None
            if priority_tag and forum.available_tags:
                priority_tag_lower = priority_tag.lower()
                for tag_obj in forum.available_tags:
                    if tag_obj.name.lower() == priority_tag_lower:
                        if tag_obj.emoji:
                            if isinstance(tag_obj.emoji, str):
                                priority_tag_emoji = tag_obj.emoji
                            else:
                                priority_tag_emoji = str(tag_obj.emoji)
                        break
            
            # Sort tags: preferred tags in order, then others alphabetically
            if preferred_tags:
                # Create ordered list: preferred tags first (in order), then others
                sorted_tags = []
                preferred_lower = [pt.lower() for pt in preferred_tags]
                
                # Add preferred tags in order
                for pref_tag in preferred_tags:
                    # Find matching tag in grouped keys (case-insensitive)
                    matching = next((t for t in grouped.keys() if t.lower() == pref_tag.lower()), None)
                    if matching:
                        sorted_tags.append(matching)
                
                # Add remaining tags alphabetically
                remaining = [t for t in grouped.keys() if t.lower() not in preferred_lower]
                sorted_tags.extend(sorted(remaining, key=lambda x: x.lower()))
            else:
                sorted_tags = sorted(grouped.keys(), key=lambda x: x.lower())
            
            for tag in sorted_tags:
                # Sort threads: priority-tagged first, then alphabetically
                def sort_key(thread):
                    has_priority = False
                    if priority_tag:
                        thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                        has_priority = priority_tag.lower() in thread_tag_names
                    # Return tuple: (not has_priority, name) - False sorts before True
                    return (not has_priority, thread.name.lower())
                
                threads_in_tag = sorted(grouped[tag], key=sort_key)
                # Get emoji for this tag if available
                tag_emoji = tag_emoji_map.get(tag.lower(), None)
                emoji_str = f"{tag_emoji} " if tag_emoji else ""
                lines.append(f"# {emoji_str}{tag}")
                for thread in threads_in_tag:
                    # Check if thread has priority tag
                    thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                    has_priority = priority_tag and priority_tag.lower() in thread_tag_names
                    
                    # Add priority emoji if applicable
                    entry_prefix = f"{priority_tag_emoji} " if (has_priority and priority_tag_emoji) else ""
                    lines.append(f"- {entry_prefix}[{thread.name}]({thread.jump_url})")
                lines.append("")
            
            text = "\n".join(lines).strip()
        else:
            # Simple alphabetical list with priority support
            # Get priority tag emoji if priority tag is set
            priority_tag_emoji = None
            if priority_tag and forum.available_tags:
                priority_tag_lower = priority_tag.lower()
                for tag_obj in forum.available_tags:
                    if tag_obj.name.lower() == priority_tag_lower:
                        if tag_obj.emoji:
                            if isinstance(tag_obj.emoji, str):
                                priority_tag_emoji = tag_obj.emoji
                            else:
                                priority_tag_emoji = str(tag_obj.emoji)
                        break
            
            # Sort threads: priority-tagged first, then alphabetically
            def sort_key(thread):
                has_priority = False
                if priority_tag:
                    thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                    has_priority = priority_tag.lower() in thread_tag_names
                # Return tuple: (not has_priority, name) - False sorts before True
                return (not has_priority, thread.name.lower())
            
            lines = []
            for thread in sorted(threads, key=sort_key):
                # Check if thread has priority tag
                thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                has_priority = priority_tag and priority_tag.lower() in thread_tag_names
                
                # Add priority emoji if applicable
                entry_prefix = f"{priority_tag_emoji} " if (has_priority and priority_tag_emoji) else ""
                lines.append(f"- {entry_prefix}[{thread.name}]({thread.jump_url})")
            text = "\n".join(lines)
        
        # Split into chunks (Discord message limit is 2000, we use 1900 for safety)
        chunks = []
        if len(text) <= 1900:
            chunks = [text] if text else ["No entries found."]
        else:
            # Split by sections if possible (when grouped by tags or title pattern)
            if sort_by_tags or sort_by_title_pattern:
                sections = text.split("\n# ")
                current_chunk = ""
                for i, section in enumerate(sections):
                    if i > 0:
                        section = "# " + section
                    
                    if len(current_chunk) + len(section) + 2 <= 1900:
                        current_chunk += ("\n" if current_chunk else "") + section
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = section
                
                if current_chunk:
                    chunks.append(current_chunk.strip())
            else:
                # Simple line-by-line splitting
                lines_list = text.split("\n")
                current_chunk = ""
                for line in lines_list:
                    if len(current_chunk) + len(line) + 1 <= 1900:
                        current_chunk += ("\n" if current_chunk else "") + line
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = line
                
                if current_chunk:
                    chunks.append(current_chunk.strip())
        
        return chunks or ["No entries found."]
    
    async def _build_title_pattern_index_text(self, forum: discord.ForumChannel, threads: List[discord.Thread], 
                                               title_grouping_pattern: str, priority_tag: Optional[str] = None) -> List[str]:
        """Build index text grouped by title pattern (e.g., suffix like '582' in 'WD1-582')."""
        
        # Get priority tag emoji if priority tag is set
        priority_tag_emoji = None
        if priority_tag and forum.available_tags:
            priority_tag_lower = priority_tag.lower()
            for tag_obj in forum.available_tags:
                if tag_obj.name.lower() == priority_tag_lower:
                    if tag_obj.emoji:
                        if isinstance(tag_obj.emoji, str):
                            priority_tag_emoji = tag_obj.emoji
                        else:
                            priority_tag_emoji = str(tag_obj.emoji)
                    break
        
        # Group threads by extracted grouping key from title
        # Store both the group key and a representative full pattern for sorting
        grouped = {}  # {group_key: (threads_list, sort_key)}
        ungrouped = []
        
        for thread in threads:
            group_key = self._extract_title_group_key(thread.name, title_grouping_pattern)
            
            # Check if thread has priority tag
            thread_tag_names = [t.name.lower() for t in thread.applied_tags]
            has_priority = priority_tag and priority_tag.lower() in thread_tag_names
            
            if group_key:
                # If group_key is just a number (from date-number pattern), extract full pattern for sorting
                sort_key = group_key
                if title_grouping_pattern.lower() == "date-number":
                    # Extract the full date pattern from the thread title for sorting
                    full_pattern_match = re.search(r'([A-Z]{2,4}\d+-\d+)', thread.name, re.IGNORECASE)
                    if full_pattern_match:
                        sort_key = full_pattern_match.group(1).upper()
                
                if group_key not in grouped:
                    grouped[group_key] = ([], sort_key)
                grouped[group_key][0].append((thread, has_priority))
            else:
                # Threads that don't match the pattern go into ungrouped
                ungrouped.append((thread, has_priority))
        
        # Build output lines grouped by pattern key
        lines = []
        
        # Sort group keys intelligently using the sort_key (full pattern if available)
        def sort_group_key(key_and_data):
            group_key, (threads_list, sort_key) = key_and_data
            sort_key_str = str(sort_key)
            
            # Try to match date pattern like "SD1-582" or "WD2-582"
            date_match = re.match(r'([A-Z]{2,4})(\d+)-(\d+)', sort_key_str, re.IGNORECASE)
            if date_match:
                prefix = date_match.group(1).upper()
                day_num = int(date_match.group(2))
                date_num = int(date_match.group(3))
                # Sort by prefix alphabetically, then by date number, then by day number
                return (0, prefix, date_num, day_num)
            
            # Try to extract numeric suffix for sorting (for patterns like "582")
            num_match = re.search(r'(\d+)$', sort_key_str)
            if num_match:
                return (1, int(num_match.group(1)))  # Sort by suffix number
            
            # Try to extract any numeric part
            any_num_match = re.search(r'\d+', sort_key_str)
            if any_num_match:
                return (2, int(any_num_match.group()))  # Sort by first number found
            
            return (3, sort_key_str.lower())  # Then alphabetical
        
        sorted_groups = sorted(grouped.items(), key=sort_group_key)
        
        for group_key, (threads_in_group, _) in sorted_groups:
            
            # Sort threads within group: priority first, then alphabetically by title
            def sort_key(item):
                thread, has_prio = item
                return (not has_prio, thread.name.lower())
            
            threads_in_group_sorted = sorted(threads_in_group, key=sort_key)
            
            # Use group key as header (format nicely)
            lines.append(f"# {group_key}")
            
            for thread, has_priority in threads_in_group_sorted:
                # Add priority emoji if applicable
                entry_prefix = f"{priority_tag_emoji} " if (has_priority and priority_tag_emoji) else ""
                lines.append(f"- {entry_prefix}[{thread.name}]({thread.jump_url})")
            
            lines.append("")
        
        # Add ungrouped threads at the end if any
        if ungrouped:
            # Sort ungrouped: priority first, then alphabetically
            def sort_ungrouped(item):
                thread, has_prio = item
                return (not has_prio, thread.name.lower())
            
            ungrouped_sorted = sorted(ungrouped, key=sort_ungrouped)
            
            lines.append("# Other")
            for thread, has_priority in ungrouped_sorted:
                entry_prefix = f"{priority_tag_emoji} " if (has_priority and priority_tag_emoji) else ""
                lines.append(f"- {entry_prefix}[{thread.name}]({thread.jump_url})")
            lines.append("")
        
        text = "\n".join(lines).strip()
        
        # Split into chunks (Discord message limit is 2000, we use 1900 for safety)
        chunks = []
        if len(text) <= 1900:
            chunks = [text] if text else ["No entries found."]
        else:
            # Split by sections
            sections = text.split("\n# ")
            current_chunk = ""
            for i, section in enumerate(sections):
                if i > 0:
                    section = "# " + section
                
                if len(current_chunk) + len(section) + 2 <= 1900:
                    current_chunk += ("\n" if current_chunk else "") + section
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = section
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        
        return chunks or ["No entries found."]
    
    async def _build_character_index_text(self, forum: discord.ForumChannel, threads: List[discord.Thread], preferred_tags: List[str], priority_tag: Optional[str] = None) -> List[str]:
        """Build character index with court-based sorting (old logic)."""
        
        # Get priority tag emoji if priority tag is set
        priority_tag_emoji = None
        if priority_tag and forum.available_tags:
            priority_tag_lower = priority_tag.lower()
            for tag_obj in forum.available_tags:
                if tag_obj.name.lower() == priority_tag_lower:
                    if tag_obj.emoji:
                        if isinstance(tag_obj.emoji, str):
                            priority_tag_emoji = tag_obj.emoji
                        else:
                            priority_tag_emoji = str(tag_obj.emoji)
                    break
        # Build court order from preferred tags if provided, otherwise use default
        if preferred_tags:
            # Map preferred tags to court headers
            COURT_MAP = {
                "night": "💫 Night Court",
                "day": "☀️ Day Court",
                "dawn": "🌄 Dawn Court",
                "spring": "🌿 Spring Court",
                "summer": "🌊 Summer Court",
                "autumn": "🍁 Autumn Court",
                "winter": "❄️ Winter Court",
            }
            COURT_ORDER = []
            for tag in preferred_tags:
                tag_lower = tag.lower()
                # Check if it's a court tag
                for court_key, header in COURT_MAP.items():
                    if court_key in tag_lower:
                        COURT_ORDER.append((court_key, header))
                        break
                # Handle inactive separately
                if "inactive" in tag_lower and ("inactive", "Inactive Characters") not in COURT_ORDER:
                    COURT_ORDER.append(("inactive", "Inactive Characters"))
        else:
            # Default court order
            COURT_ORDER = [
                ("night", "💫 Night Court"),
                ("day", "☀️ Day Court"),
                ("dawn", "🌄 Dawn Court"),
                ("spring", "🌿 Spring Court"),
                ("summer", "🌊 Summer Court"),
                ("autumn", "🍁 Autumn Court"),
                ("winter", "❄️ Winter Court"),
            ]
            COURT_ORDER.append(("inactive", "Inactive Characters"))
        
        grouped = {court: {"council": [], "members": []} for court, _ in COURT_ORDER}
        other = []
        inactive = []
        
        for thread in threads:
            # Normalize tag names (for court detection)
            tag_names = []
            # Also keep actual tag names for priority tag checking
            actual_tag_names = []
            for t in thread.applied_tags:
                actual_tag_names.append(t.name)
                tag = t.name.lower()
                if tag.startswith("the "):
                    tag = tag[4:]
                if tag.endswith(" court"):
                    tag = tag[:-6]
                tag = tag.strip()
                tag_names.append(tag)
            
            url = thread.jump_url
            is_council = any("high council" in tn for tn in tag_names)
            is_inactive = any("inactive" in tn for tn in tag_names)
            
            # Check if thread has priority tag (use actual tag names, not normalized)
            actual_tag_names_lower = [tn.lower() for tn in actual_tag_names]
            has_priority = priority_tag and priority_tag.lower() in actual_tag_names_lower
            
            # Format entry with priority emoji if applicable
            priority_prefix = f"{priority_tag_emoji} " if (has_priority and priority_tag_emoji) else ""
            if is_council:
                entry = f"👑 {priority_prefix}[{thread.name}]({url})"
            else:
                entry = f"- {priority_prefix}[{thread.name}]({url})"
            
            # Court detection
            court = next((c for c, _ in COURT_ORDER if c in tag_names), None)
            if is_inactive:
                inactive.append((entry, has_priority))
            elif court:
                if is_council:
                    grouped[court]["council"].append((entry, has_priority))
                else:
                    grouped[court]["members"].append((entry, has_priority))
            else:
                other.append((entry, has_priority))
        
        # Build output lines
        lines = []
        for court, header in COURT_ORDER:
            if court == "inactive":
                continue  # Handle inactive separately
            court_council = grouped[court]["council"]
            court_members = grouped[court]["members"]
            
            # Sort: priority first, then alphabetically by entry name
            def sort_entries(entry_tuple):
                entry_text, has_prio = entry_tuple
                # Extract name from entry (e.g., "👑 👑 [Name](url)" -> "Name")
                # Try to find name between [ and ](
                try:
                    name_start = entry_text.find("[") + 1
                    name_end = entry_text.find("](")
                    if name_start > 0 and name_end > name_start:
                        name = entry_text[name_start:name_end]
                    else:
                        name = entry_text
                except:
                    name = entry_text
                return (not has_prio, name.lower())
            
            court_council_sorted = sorted(court_council, key=sort_entries)
            court_members_sorted = sorted(court_members, key=sort_entries)
            court_entries = [e[0] for e in court_council_sorted] + [e[0] for e in court_members_sorted]
            
            if court_entries:
                lines.append(f"# {header}")
                lines.extend(court_entries)
                lines.append("")
        
        if inactive:
            # Sort inactive entries by priority, then alphabetically
            def sort_entries_inactive(entry_tuple):
                entry_text, has_prio = entry_tuple
                # Extract name from entry (e.g., "- 👑 [Name](url)" -> "Name")
                try:
                    name_start = entry_text.find("[") + 1
                    name_end = entry_text.find("](")
                    if name_start > 0 and name_end > name_start:
                        name = entry_text[name_start:name_end]
                    else:
                        name = entry_text
                except:
                    name = entry_text
                return (not has_prio, name.lower())
            
            inactive_sorted = sorted(inactive, key=sort_entries_inactive)
            inactive_entries = [e[0] for e in inactive_sorted]
            lines.append("# Inactive Characters")
            lines.extend(inactive_entries)
            lines.append("")
        
        if other:
            # Sort other entries by priority, then alphabetically
            def sort_entries_other(entry_tuple):
                entry_text, has_prio = entry_tuple
                # Extract name from entry (e.g., "- 👑 [Name](url)" -> "Name")
                try:
                    name_start = entry_text.find("[") + 1
                    name_end = entry_text.find("](")
                    if name_start > 0 and name_end > name_start:
                        name = entry_text[name_start:name_end]
                    else:
                        name = entry_text
                except:
                    name = entry_text
                return (not has_prio, name.lower())
            
            other_sorted = sorted(other, key=sort_entries_other)
            other_entries = [e[0] for e in other_sorted]
            lines.append("# Other")
            lines.extend(other_entries)
        
        text = "\n".join(lines).strip()
        
        # Split into chunks
        chunks = []
        if len(text) <= 1900:
            chunks = [text] if text else ["No entries found."]
        else:
            # Split by sections
            sections = text.split("\n# ")
            current_chunk = ""
            for i, section in enumerate(sections):
                if i > 0:
                    section = "# " + section
                
                if len(current_chunk) + len(section) + 2 <= 1900:
                    current_chunk += ("\n" if current_chunk else "") + section
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = section
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        
        return chunks or ["No entries found."]
    
    def _get_group_index_key(self, guild_id: int, target_channel_id: int) -> str:
        """Get the key for a group index."""
        return f"{guild_id}:{target_channel_id}"
    
    async def build_group_index(self, guild: discord.Guild, target_channel: Union[discord.TextChannel, discord.ForumChannel], config: dict):
        """Build a group index combining multiple forums."""
        source_forum_ids = config.get("source_forum_ids", [])
        if not source_forum_ids:
            return
        
        # Collect all threads from all source forums
        all_threads = []
        forum_config_map = {}  # Map forum_id to individual forum config
        
        for forum_id in source_forum_ids:
            forum = guild.get_channel(forum_id)
            if not forum or not isinstance(forum, discord.ForumChannel):
                continue
            
            # Use same config options as regular index
            forum_config = {
                "sort_by_tags": config.get("sort_by_tags", False),
                "preferred_tags": config.get("preferred_tags", []),
                "use_character_sorting": config.get("use_character_sorting", False),
                "priority_tag": config.get("priority_tag"),
                "sort_by_title_pattern": config.get("sort_by_title_pattern", False),
                "title_grouping_pattern": config.get("title_grouping_pattern")
            }
            forum_config_map[forum_id] = forum_config
            
            # Collect threads from this forum
            active_threads = list(forum.threads)
            archived_threads = await rate_limited_archived_threads(forum, limit=None, delay_between_pages=0.5)
            
            for thread in active_threads + archived_threads:
                if thread.name.lower() not in [name.lower() for name in DEFAULT_EXCLUDE_NAMES]:
                    all_threads.append((forum, thread))
        
        if not all_threads:
            return
        
        # If target is a forum channel, create/update threads for each group
        if isinstance(target_channel, discord.ForumChannel):
            await self._build_group_index_as_threads(guild, target_channel, all_threads, config, forum_config_map)
        else:
            # Normal channel: build as chunks
            await self._build_group_index_as_chunks(guild, target_channel, all_threads, config, forum_config_map)
    
    async def _build_group_index_as_chunks(self, guild: discord.Guild, target_channel: discord.TextChannel,
                                           all_threads: List[tuple], config: dict, forum_config_map: dict):
        """Build group index in a normal channel as message chunks."""
        # Create a mapping of thread -> forum for adding forum names
        thread_to_forum = {thread: forum for forum, thread in all_threads}
        
        # Use the first forum for tag/emoji info
        first_forum = all_threads[0][0] if all_threads else None
        if not first_forum:
            return
        
        # Build index text using existing logic, then add forum names
        if config.get("use_character_sorting"):
            chunks = await self._build_character_index_text(
                first_forum, [thread for _, thread in all_threads],
                config.get("preferred_tags", []),
                config.get("priority_tag")
            )
            chunks = self._add_forum_names_to_chunks(chunks, thread_to_forum)
        elif config.get("sort_by_title_pattern") and config.get("title_grouping_pattern"):
            chunks = await self._build_title_pattern_index_text(
                first_forum, [thread for _, thread in all_threads],
                config.get("title_grouping_pattern"),
                config.get("priority_tag")
            )
            chunks = self._add_forum_names_to_chunks(chunks, thread_to_forum)
        elif config.get("sort_by_tags"):
            # Reuse existing tag-based grouping logic
            chunks = await self._build_tag_index_text(
                first_forum, [thread for _, thread in all_threads],
                config.get("preferred_tags", []),
                config.get("priority_tag")
            )
            chunks = self._add_forum_names_to_chunks(chunks, thread_to_forum)
        else:
            # Simple alphabetical list
            chunks = await self._build_simple_index_text(
                first_forum, [thread for _, thread in all_threads],
                config.get("priority_tag")
            )
            chunks = self._add_forum_names_to_chunks(chunks, thread_to_forum)
        
        # Get or create index message
        group_key = self._get_group_index_key(guild.id, target_channel.id)
        intro_text = config.get("intro_text", "Group Index")
        
        # Try to find existing intro message
        async for message in target_channel.history(limit=100):
            if message.author == self.bot.user and message.content == intro_text:
                # Found intro message, update chunks after it
                chunk_index = 1
                for chunk in chunks:
                    try:
                        async for msg in target_channel.history(after=message, limit=50):
                            if msg.author == self.bot.user and msg.id != message.id:
                                if chunk_index <= len(chunks):
                                    await rate_limit_retry(msg.edit, max_retries=5, base_delay=2.0, content=chunk)
                                    chunk_index += 1
                                    await asyncio.sleep(1.0)
                                    break
                        else:
                            # Need to create new message
                            await rate_limit_retry(target_channel.send, max_retries=5, base_delay=2.0, content=chunk)
                            await asyncio.sleep(1.5)
                            chunk_index += 1
                    except Exception as e:
                        print(f"[GroupIndex] Error updating chunk: {e}")
                return
        
        # No existing message found, create new
        try:
            await rate_limit_retry(target_channel.send, max_retries=5, base_delay=2.0, content=intro_text)
            await asyncio.sleep(1.5)
            for chunk in chunks:
                await rate_limit_retry(target_channel.send, max_retries=5, base_delay=2.0, content=chunk)
                await asyncio.sleep(1.5)
        except Exception as e:
            print(f"[GroupIndex] Error creating group index: {e}")
    
    async def _build_tag_index_text(self, forum: discord.ForumChannel, threads: List[discord.Thread],
                                    preferred_tags: List[str], priority_tag: Optional[str]) -> List[str]:
        """Build tag-based index text (reused from build_index_text logic)."""
        grouped = {}
        for thread in threads:
            tag_names = [tag.name for tag in thread.applied_tags]
            
            if preferred_tags:
                matching_tags = [tag for tag in tag_names if tag.lower() in [pt.lower() for pt in preferred_tags]]
                tag = matching_tags[0] if matching_tags else "Other"
            else:
                tag = tag_names[0] if tag_names else "Other"
            
            grouped.setdefault(tag, []).append(thread)
        
        lines = []
        sorted_tags = sorted(grouped.keys(), key=lambda x: x.lower())
        
        for tag in sorted_tags:
            def sort_key(thread):
                has_priority = False
                if priority_tag:
                    thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                    has_priority = priority_tag.lower() in thread_tag_names
                return (not has_priority, thread.name.lower())
            
            threads_in_tag = sorted(grouped[tag], key=sort_key)
            lines.append(f"# {tag}")
            for thread in threads_in_tag:
                lines.append(f"- [{thread.name}]({thread.jump_url})")
            lines.append("")
        
        text = "\n".join(lines).strip()
        return [text] if len(text) <= 1900 else self._split_text_into_chunks(text)
    
    async def _build_simple_index_text(self, forum: discord.ForumChannel, threads: List[discord.Thread],
                                       priority_tag: Optional[str]) -> List[str]:
        """Build simple alphabetical index text."""
        def sort_key(thread):
            has_priority = False
            if priority_tag:
                thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                has_priority = priority_tag.lower() in thread_tag_names
            return (not has_priority, thread.name.lower())
        
        lines = []
        for thread in sorted(threads, key=sort_key):
            lines.append(f"- [{thread.name}]({thread.jump_url})")
        
        text = "\n".join(lines)
        return [text] if len(text) <= 1900 else self._split_text_into_chunks(text)
    
    def _add_forum_names_to_chunks(self, chunks: List[str], thread_to_forum: Dict[discord.Thread, discord.ForumChannel]) -> List[str]:
        """Add forum names to thread links in chunks for group indexes."""
        updated_chunks = []
        
        for chunk in chunks:
            lines = chunk.split("\n")
            updated_lines = []
            
            for line in lines:
                # Match thread link pattern: - [thread name](url) or - emoji [thread name](url)
                # Pattern: - (optional prefix) [thread_name](jump_url)
                link_pattern = r'(-\s*(?:[^\s]+\s+)?)\[(.+?)\]\((.+?)\)'
                
                def replace_with_forum(match):
                    prefix = match.group(1)  # Includes the "- " and any emoji
                    thread_name = match.group(2)
                    jump_url = match.group(3)
                    
                    # Find the thread by matching jump_url (contains thread ID)
                    thread_id_match = re.search(r'/(\d+)/?$', jump_url)
                    if thread_id_match:
                        thread_id = int(thread_id_match.group(1))
                        # Find thread in mapping
                        for thread, forum in thread_to_forum.items():
                            if thread.id == thread_id:
                                forum_name = forum.name if forum else "Unknown"
                                return f"{prefix}**{forum_name}** - [{thread_name}]({jump_url})"
                    
                    # If we can't find by ID, try matching by name as fallback
                    for thread, forum in thread_to_forum.items():
                        if thread.name == thread_name:
                            forum_name = forum.name if forum else "Unknown"
                            return f"{prefix}**{forum_name}** - [{thread_name}]({jump_url})"
                    
                    # If no match found, return original
                    return match.group(0)
                
                updated_line = re.sub(link_pattern, replace_with_forum, line)
                updated_lines.append(updated_line)
            
            updated_chunks.append("\n".join(updated_lines))
        
        return updated_chunks
    
    def _split_text_into_chunks(self, text: str, max_length: int = 1900) -> List[str]:
        """Split text into chunks respecting max length."""
        chunks = []
        lines_list = text.split("\n")
        current_chunk = ""
        
        for line in lines_list:
            if len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk += ("\n" if current_chunk else "") + line
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks or ["No entries found."]
    
    async def _build_group_index_as_threads(self, guild: discord.Guild, target_forum: discord.ForumChannel,
                                           all_threads: List[tuple], config: dict, forum_config_map: dict):
        """Build group index in a forum channel - creates one thread per group/entry."""
        group_key = self._get_group_index_key(guild.id, target_forum.id)
        
        # Group threads based on config
        if config.get("sort_by_title_pattern") and config.get("title_grouping_pattern"):
            # Group by title pattern
            groups = {}
            for forum, thread in all_threads:
                group_key_extracted = self._extract_title_group_key(thread.name, config["title_grouping_pattern"])
                if group_key_extracted:
                    groups.setdefault(group_key_extracted, []).append((forum, thread))
                else:
                    groups.setdefault("Other", []).append((forum, thread))
        elif config.get("sort_by_tags"):
            # Group by tags
            groups = {}
            preferred_tags = config.get("preferred_tags", [])
            for forum, thread in all_threads:
                tag_names = [tag.name for tag in thread.applied_tags]
                if preferred_tags:
                    matching_tags = [tag for tag in tag_names if tag.lower() in [pt.lower() for pt in preferred_tags]]
                    group = matching_tags[0] if matching_tags else "Other"
                else:
                    group = tag_names[0] if tag_names else "Other"
                groups.setdefault(group, []).append((forum, thread))
        else:
            # Single group with all threads
            groups = {"All Threads": all_threads}
        
        # Create or update threads for each group
        thread_map = {}
        if group_key not in self.group_index_thread_ids:
            self.group_index_thread_ids[group_key] = {}
        
        existing_threads = {t.name: t for t in target_forum.threads}
        
        for group_name, threads_list in groups.items():
            thread_name = f"📜 {config.get('group_index_name', 'Index')} - {group_name}"
            
            # Build content for this thread
            lines = []
            
            # Sort threads within group (keep forum info)
            priority_tag = config.get("priority_tag")
            def sort_key(forum_thread_tuple):
                forum, thread = forum_thread_tuple
                has_priority = False
                if priority_tag:
                    thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                    has_priority = priority_tag.lower() in thread_tag_names
                return (not has_priority, thread.name.lower())
            
            sorted_threads_with_forums = sorted(threads_list, key=sort_key)
            
            for forum, thread in sorted_threads_with_forums:
                entry_prefix = ""
                if priority_tag:
                    thread_tag_names = [t.name.lower() for t in thread.applied_tags]
                    if priority_tag.lower() in thread_tag_names:
                        # Try to get emoji for priority tag
                        if hasattr(forum, 'available_tags'):
                            for tag_obj in forum.available_tags:
                                if tag_obj.name.lower() == priority_tag.lower() and tag_obj.emoji:
                                    entry_prefix = f"{tag_obj.emoji} "
                                    break
                
                # Include origin forum name
                forum_name = forum.name if forum else "Unknown"
                lines.append(f"- {entry_prefix}**{forum_name}** - [{thread.name}]({thread.jump_url})")
            
            content = "\n".join(lines) if lines else "No entries found."
            
            # Create or update thread
            thread_id_key = group_name
            if thread_id_key in self.group_index_thread_ids[group_key]:
                # Try to update existing thread (by ID - most reliable)
                thread_id = self.group_index_thread_ids[group_key][thread_id_key]
                thread = target_forum.get_thread(thread_id)
                if thread:
                    try:
                        # Check if thread name needs updating (in case group_index_name changed)
                        if thread.name != thread_name:
                            # Rename thread instead of recreating it
                            await rate_limit_retry(thread.edit, max_retries=5, base_delay=2.0, name=thread_name)
                        
                        # Update content
                        messages = await rate_limited_message_history(thread, limit=10)  # Get more messages to find non-system message
                        # Find the first non-system message (system messages can't be edited)
                        message_to_edit = None
                        for msg in messages:
                            if msg.type == discord.MessageType.default or msg.type == discord.MessageType.chat_input_command:
                                message_to_edit = msg
                                break
                        
                        if message_to_edit:
                            await rate_limit_retry(message_to_edit.edit, max_retries=5, base_delay=2.0, content=content)
                        else:
                            # No editable message found, send a new one
                            await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=content)
                    except Exception as e:
                        print(f"[GroupIndex] Error updating thread {thread_name}: {e}")
                else:
                    # Thread not found by ID, might have been deleted
                    # Try to find by exact name match first
                    if thread_name in existing_threads:
                        thread = existing_threads[thread_name]
                        self.group_index_thread_ids[group_key][thread_id_key] = thread.id
                        try:
                            messages = await rate_limited_message_history(thread, limit=10)
                            # Find the first non-system message (system messages can't be edited)
                            message_to_edit = None
                            for msg in messages:
                                if msg.type == discord.MessageType.default or msg.type == discord.MessageType.chat_input_command:
                                    message_to_edit = msg
                                    break
                            
                            if message_to_edit:
                                await rate_limit_retry(message_to_edit.edit, max_retries=5, base_delay=2.0, content=content)
                            else:
                                # No editable message found, send a new one
                                await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=content)
                        except Exception as e:
                            print(f"[GroupIndex] Error updating thread {thread_name}: {e}")
                    else:
                        # Check if there's an old thread with the same group_name but different group_index_name
                        # Look for threads that end with " - {group_name}" pattern
                        old_thread_found = False
                        for existing_thread_name, existing_thread in existing_threads.items():
                            # Check if this thread ends with our group_name (might have old group_index_name)
                            if existing_thread_name.endswith(f" - {group_name}"):
                                # This is likely our thread with an old name - rename it
                                try:
                                    await rate_limit_retry(existing_thread.edit, max_retries=5, base_delay=2.0, name=thread_name)
                                    self.group_index_thread_ids[group_key][thread_id_key] = existing_thread.id
                                    messages = await rate_limited_message_history(existing_thread, limit=10)
                                    # Find the first non-system message (system messages can't be edited)
                                    message_to_edit = None
                                    for msg in messages:
                                        if msg.type == discord.MessageType.default or msg.type == discord.MessageType.chat_input_command:
                                            message_to_edit = msg
                                            break
                                    
                                    if message_to_edit:
                                        await rate_limit_retry(message_to_edit.edit, max_retries=5, base_delay=2.0, content=content)
                                    else:
                                        # No editable message found, send a new one
                                        await rate_limit_retry(existing_thread.send, max_retries=5, base_delay=2.0, content=content)
                                    old_thread_found = True
                                    break
                                except Exception as e:
                                    print(f"[GroupIndex] Error renaming old thread {existing_thread_name} to {thread_name}: {e}")
                        
                        if not old_thread_found:
                            # Create new thread
                            thread = await self._create_group_index_thread(target_forum, thread_name, content)
                            if thread:
                                self.group_index_thread_ids[group_key][thread_id_key] = thread.id
            elif thread_name in existing_threads:
                # Use existing thread with matching name
                thread = existing_threads[thread_name]
                self.group_index_thread_ids[group_key][thread_id_key] = thread.id
                try:
                    messages = await rate_limited_message_history(thread, limit=1)
                    if messages:
                        await rate_limit_retry(messages[0].edit, max_retries=5, base_delay=2.0, content=content)
                except Exception as e:
                    print(f"[GroupIndex] Error updating thread {thread_name}: {e}")
            else:
                # Check if there's an old thread with the same group_name but different group_index_name
                # Look for threads that end with " - {group_name}" pattern
                old_thread_found = False
                for existing_thread_name, existing_thread in existing_threads.items():
                    # Check if this thread ends with our group_name (might have old group_index_name)
                    if existing_thread_name.endswith(f" - {group_name}"):
                        # This is likely our thread with an old name - rename it
                        try:
                            await rate_limit_retry(existing_thread.edit, max_retries=5, base_delay=2.0, name=thread_name)
                            self.group_index_thread_ids[group_key][thread_id_key] = existing_thread.id
                            messages = await rate_limited_message_history(existing_thread, limit=1)
                            if messages:
                                await rate_limit_retry(messages[0].edit, max_retries=5, base_delay=2.0, content=content)
                            old_thread_found = True
                            break
                        except Exception as e:
                            print(f"[GroupIndex] Error renaming old thread {existing_thread_name} to {thread_name}: {e}")
                
                if not old_thread_found:
                    # Create new thread
                    thread = await self._create_group_index_thread(target_forum, thread_name, content)
                    if thread:
                        self.group_index_thread_ids[group_key][thread_id_key] = thread.id
        
        # Handle thread sorting if target is forum
        thread_sort_by = config.get("thread_sort_by", "creation")
        if thread_sort_by == "tag" and config.get("thread_sort_tag"):
            # Sort threads by tag (would need manual pinning or other Discord features)
            # For now, we'll just ensure threads are created/updated
            pass
    
    async def _create_group_index_thread(self, forum: discord.ForumChannel, name: str, content: str) -> Optional[discord.Thread]:
        """Create a new thread in a forum for group index."""
        try:
            thread_with_msg = await rate_limit_retry(
                forum.create_thread,
                max_retries=5,
                base_delay=2.0,
                name=name,
                content=content
            )
            return thread_with_msg.thread
        except Exception as e:
            print(f"[GroupIndex] Error creating thread {name}: {e}")
            return None
    
    async def ensure_index_thread(self, guild: discord.Guild, forum: discord.ForumChannel, config: dict) -> Optional[discord.Thread]:
        """Ensure the index thread exists, creating it if necessary."""
        index_key = self._get_index_key(guild.id, forum.id)
        index_thread_name = config.get("index_thread_name", "Index")
        intro_text = config.get("intro_text", "Index")
        thumb_url = config.get("thumb_url")
        
        # Check cache first
        if index_key in self.index_thread_ids:
            thread = forum.get_thread(self.index_thread_ids[index_key])
            if thread:
                return thread
        
        # Look for existing thread
        for thread in forum.threads:
            if thread.name == index_thread_name:
                self.index_thread_ids[index_key] = thread.id
                return thread
        
        # Use rate-limited archived threads fetching
        archived_threads = await rate_limited_archived_threads(forum, limit=None, delay_between_pages=0.5)
        for thread in archived_threads:
            if thread.name == index_thread_name:
                self.index_thread_ids[index_key] = thread.id
                return thread
        
        # Create new thread with rate limit protection
        embed = None
        if thumb_url:
            embed = discord.Embed().set_thumbnail(url=thumb_url)
        
        try:
            thread_with_msg = await rate_limit_retry(
                forum.create_thread,
                max_retries=5,
                base_delay=2.0,
                name=index_thread_name,
                content=intro_text,
                embed=embed
            )
            self.index_thread_ids[index_key] = thread_with_msg.thread.id
            return thread_with_msg.thread
        except Exception as e:
            print(f"[IndexManager] Failed to create index thread: {e}")
            return None
    
    async def post_or_edit_index(self, guild: discord.Guild, forum: discord.ForumChannel, config: dict):
        """Post or update an index."""
        index_key = self._get_index_key(guild.id, forum.id)
        
        thread = await self.ensure_index_thread(guild, forum, config)
        if not thread:
            return
        
        # If thread was just created, wait a moment for the initial message to be fully available
        await asyncio.sleep(1.0)
        
        chunks = await self.build_index_text(forum, config)
        
        # Check if content changed
        if chunks == self.last_chunks.get(index_key, []):
            print(f"[IndexManager] No changes detected for index {index_key}, skipping update")
            return
        
        self.last_chunks[index_key] = chunks
        
        # Get existing messages with rate limiting
        # Discord returns messages newest-first, so reverse to get chronological order (oldest first)
        messages = await rate_limited_message_history(thread, limit=None, delay_between_pages=0.3)
        messages.reverse()  # Reverse to chronological order: messages[0] = oldest (intro), messages[1+] = chunks
        
        intro_text = config.get("intro_text", "Index")
        
        print(f"[IndexManager] Updating index {index_key}: {len(chunks)} chunks, {len(messages)} existing messages")
        
        # Ensure we have chunks to post
        if not chunks:
            print(f"[IndexManager] Warning: No chunks to post for index {index_key}")
            return
        
        if messages:
            # Step 1: Ensure first message contains intro text
            # Find the first non-system message (system messages can't be edited)
            message_to_edit_intro = None
            for msg in messages:
                if msg.type == discord.MessageType.default or msg.type == discord.MessageType.chat_input_command:
                    message_to_edit_intro = msg
                    break
            
            if message_to_edit_intro and message_to_edit_intro.content != intro_text:
                try:
                    await rate_limit_retry(message_to_edit_intro.edit, max_retries=5, base_delay=2.0, content=intro_text)
                    await asyncio.sleep(1.0)  # Delay after intro edit
                except Exception as e:
                    print(f"[IndexManager] Error editing intro message: {e}")
            elif not message_to_edit_intro:
                # No editable message found, send intro as new message
                try:
                    await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=intro_text)
                    await asyncio.sleep(1.0)
                except Exception as e:
                    print(f"[IndexManager] Error sending intro message: {e}")
            
            # Step 2: Create missing messages first (to maintain order)
            # We need len(chunks) messages after the intro, so total should be len(chunks) + 1
            messages_needed = len(chunks) + 1  # intro + chunks
            print(f"[IndexManager] Need {messages_needed} messages total ({len(chunks)} chunks + 1 intro), have {len(messages)}")
            
            if len(messages) < messages_needed:
                # Create placeholder messages for missing ones
                missing_count = messages_needed - len(messages)
                print(f"[IndexManager] Creating {missing_count} missing placeholder messages")
                created_count = 0
                for i in range(missing_count):
                    try:
                        # Send placeholder that we'll edit immediately
                        placeholder = "..."  # Temporary placeholder
                        await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=placeholder)
                        created_count += 1
                        await asyncio.sleep(1.5)  # Longer delay between sends to avoid rate limits
                    except Exception as e:
                        print(f"[IndexManager] Error creating placeholder message {i}: {e}")
                        # Continue trying to create remaining messages even if one fails
                        continue
                
                print(f"[IndexManager] Created {created_count} placeholder messages")
                
                # Re-fetch messages to get the newly created ones
                await asyncio.sleep(2.0)  # Wait longer before refetching to ensure messages are available
                messages = await rate_limited_message_history(thread, limit=None, delay_between_pages=0.3)
                messages.reverse()  # Reverse to chronological order
                print(f"[IndexManager] After creating placeholders, now have {len(messages)} messages")
            
            # Step 3: Edit all messages in order (intro + chunks)
            # Edit intro if needed (already done, but ensure it's correct)
            # Find the first non-system message (system messages can't be edited)
            message_to_edit = None
            for msg in messages:
                if msg.type == discord.MessageType.default or msg.type == discord.MessageType.chat_input_command:
                    message_to_edit = msg
                    break
            
            if message_to_edit and message_to_edit.content != intro_text:
                try:
                    await rate_limit_retry(message_to_edit.edit, max_retries=5, base_delay=2.0, content=intro_text)
                    await asyncio.sleep(1.0)
                except Exception as e:
                    print(f"[IndexManager] Error editing intro message: {e}")
            elif not message_to_edit:
                # No editable message found, send intro as new message
                try:
                    await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=intro_text)
                    await asyncio.sleep(1.0)
                except Exception as e:
                    print(f"[IndexManager] Error sending intro message: {e}")
            
            # Edit chunk messages in order
            print(f"[IndexManager] Editing {len(chunks)} chunk messages (have {len(messages)} total messages)")
            for i, chunk in enumerate(chunks):
                msg_index = i + 1  # chunk 0 -> message 1, chunk 1 -> message 2, etc.
                if msg_index < len(messages):
                    try:
                        print(f"[IndexManager] Editing message {msg_index} (index {i}/{len(chunks)-1}) with chunk content")
                        await rate_limit_retry(messages[msg_index].edit, max_retries=5, base_delay=2.0, content=chunk)
                        # Longer delay between edits to avoid rate limits
                        if i < len(chunks) - 1:
                            await asyncio.sleep(1.5)
                    except Exception as e:
                        print(f"[IndexManager] Error editing message {msg_index} with chunk {i}: {e}")
                        import traceback
                        traceback.print_exc()
                        # Continue with next chunk even if this one fails
                        continue
                else:
                    # This shouldn't happen if we created messages above, but handle it
                    print(f"[IndexManager] Warning: msg_index {msg_index} >= {len(messages)}, sending new message for chunk {i}")
                    try:
                        await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=chunk)
                        if i < len(chunks) - 1:
                            await asyncio.sleep(1.5)
                    except Exception as e:
                        print(f"[IndexManager] Error sending chunk {i}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
            
            # Step 4: Delete extra messages (if any)
            messages_to_keep = len(chunks) + 1  # intro + chunks
            if len(messages) > messages_to_keep:
                print(f"[IndexManager] Deleting {len(messages) - messages_to_keep} extra messages")
                for j in range(messages_to_keep, len(messages)):
                    try:
                        await rate_limit_retry(messages[j].delete, max_retries=5, base_delay=2.0)
                        await asyncio.sleep(1.0)  # Longer delay between deletes
                    except Exception as e:
                        print(f"[IndexManager] Error deleting message {j}: {e}")
                        continue
        else:
            # No existing messages - create all from scratch
            print(f"[IndexManager] Creating new index thread with {len(chunks)} chunks")
            try:
                await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=intro_text)
                await asyncio.sleep(1.5)
                for i, chunk in enumerate(chunks):
                    await rate_limit_retry(thread.send, max_retries=5, base_delay=2.0, content=chunk)
                    if i < len(chunks) - 1:
                        await asyncio.sleep(1.5)  # Longer delay between sends
            except Exception as e:
                print(f"[IndexManager] Error creating new messages: {e}")
    
    async def refresh_index(self, guild_id: int, forum_id: int):
        """Refresh a specific index."""
        config = self.config.get_index(guild_id, forum_id)
        if not config:
            return False
        
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False
        
        forum = guild.get_channel(forum_id)
        if not forum or not isinstance(forum, discord.ForumChannel):
            return False
        
        await self.post_or_edit_index(guild, forum, config)
        return True
    
    async def refresh_group_index(self, guild_id: int, target_channel_id: int):
        """Refresh a specific group index."""
        config = self.config.get_group_index(guild_id, target_channel_id)
        if not config:
            return False
        
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False
        
        target_channel = guild.get_channel(target_channel_id)
        if not target_channel or not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
            return False
        
        await self.build_group_index(guild, target_channel, config)
        return True
    
    @tasks.loop(hours=6)
    async def update_index_task(self):
        """Background task to update all indexes."""
        await self.bot.wait_until_ready()
        
        # Stagger initial execution to avoid rate limits on startup
        if self._startup_delay > 0:
            await asyncio.sleep(self._startup_delay)
        
        indexes = self.config.get_indexes()
        # Process indexes sequentially with delays to avoid rate limits
        for idx, (key, config) in enumerate(indexes.items()):
            try:
                guild_id = config["guild_id"]
                forum_id = config["forum_id"]
                
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                forum = guild.get_channel(forum_id)
                if not forum or not isinstance(forum, discord.ForumChannel):
                    continue
                
                await self.post_or_edit_index(guild, forum, config)
                
                # Add delay between indexes to avoid rate limits
                if idx < len(indexes) - 1:
                    await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[IndexManager] Error updating index {key}: {e}")
    
    @update_index_task.before_loop
    async def before_update_index_task(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(hours=6)
    async def update_group_index_task(self):
        """Background task to update all group indexes."""
        await self.bot.wait_until_ready()
        
        # Stagger initial execution to avoid rate limits on startup
        if self._startup_delay > 0:
            await asyncio.sleep(self._startup_delay + 60)  # Delay after regular indexes
        
        group_indexes = self.config.get_group_indexes()
        # Process group indexes sequentially with delays to avoid rate limits
        for idx, (key, config) in enumerate(group_indexes.items()):
            try:
                guild_id = config["guild_id"]
                target_channel_id = config["target_channel_id"]
                
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                target_channel = guild.get_channel(target_channel_id)
                if not target_channel or not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
                    continue
                
                await self.build_group_index(guild, target_channel, config)
                
                # Add delay between indexes to avoid rate limits
                if idx < len(group_indexes) - 1:
                    await asyncio.sleep(5.0)  # Longer delay for group indexes
            except Exception as e:
                print(f"[IndexManager] Error updating group index {key}: {e}")
    
    @update_group_index_task.before_loop
    async def before_update_group_index_task(self):
        await self.bot.wait_until_ready()
    
    # Commands
    index_group = app_commands.Group(
        name="index",
        description="Manage forum indexes"
    )
    
    @index_group.command(name="add", description="Add a forum to index")
    @app_commands.describe(
        forum="The forum channel to index",
        index_name="Name for this index (e.g., 'Characters', 'Resources')",
        sort_by_tags="Whether to group entries by tags",
        preferred_tags="Comma-separated list of preferred tags to sort by (optional, only used if sort_by_tags is true)",
        index_thread_name="Name for the index thread (defaults to '📜 {index_name} Index')",
        intro_text="Intro text for the index thread",
        thumb_url="Thumbnail URL for the index thread",
        priority_tag="Optional tag name whose entries will appear at the top of their lists with the tag's emoji",
        sort_by_title_pattern="Whether to group entries by title pattern instead of tags",
        title_grouping_pattern="Pattern: 'date-number' extracts suffix (582) from 'SD1-582', 'date-suffix' extracts full date ('SD1-582'), 'after-' for suffix after dash, 'before-' for prefix, or regex"
    )
    @app_commands.default_permissions(administrator=True)
    async def index_add(
        self,
        interaction: discord.Interaction,
        forum: discord.ForumChannel,
        index_name: str,
        sort_by_tags: bool = False,
        preferred_tags: Optional[str] = None,
        index_thread_name: Optional[str] = None,
        intro_text: Optional[str] = None,
        thumb_url: Optional[str] = None,
        priority_tag: Optional[str] = None,
        sort_by_title_pattern: bool = False,
        title_grouping_pattern: Optional[str] = None
    ):
        """Add a forum to the index system."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Parse preferred tags
        preferred_tags_list = None
        if preferred_tags:
            preferred_tags_list = [tag.strip() for tag in preferred_tags.split(",") if tag.strip()]
        
        # Validate title pattern if provided
        if sort_by_title_pattern and not title_grouping_pattern:
            await interaction.followup.send(
                "❌ `title_grouping_pattern` is required when `sort_by_title_pattern` is true.",
                ephemeral=True
            )
            return
        
        # Add index configuration
        self.config.add_index(
            guild_id=interaction.guild.id,
            forum_id=forum.id,
            index_name=index_name,
            sort_by_tags=sort_by_tags,
            preferred_tags=preferred_tags_list,
            index_thread_name=index_thread_name,
            intro_text=intro_text,
            thumb_url=thumb_url,
            priority_tag=priority_tag,
            sort_by_title_pattern=sort_by_title_pattern,
            title_grouping_pattern=title_grouping_pattern
        )
        
        # Immediately refresh the index
        await self.refresh_index(interaction.guild.id, forum.id)
        
        tag_info = ""
        if sort_by_tags:
            if preferred_tags_list:
                tag_info = f" (sorting by tags: {', '.join(preferred_tags_list)})"
            else:
                tag_info = " (sorting by all tags)"
        elif sort_by_title_pattern:
            tag_info = f" (sorting by title pattern: {title_grouping_pattern})"
        
        priority_info = ""
        if priority_tag:
            priority_info = f" (priority tag: {priority_tag})"
        
        await interaction.followup.send(
            f"✅ Added index for **{forum.name}** ({index_name}){tag_info}{priority_info}",
            ephemeral=True
        )
    
    @index_group.command(name="refresh", description="Refresh one or all indexes")
    @app_commands.describe(
        forum="Specific forum to refresh (for regular indexes)",
        channel="Specific channel to refresh (for group indexes, use this instead of forum)"
    )
    @app_commands.default_permissions(administrator=True)
    async def index_refresh(
        self,
        interaction: discord.Interaction,
        forum: Optional[discord.ForumChannel] = None,
        channel: Optional[Union[discord.TextChannel, discord.ForumChannel]] = None
    ):
        """Refresh indexes."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Check if channel is provided (for group indexes)
        if channel:
            # Try to refresh as group index first
            group_config = self.config.get_group_index(interaction.guild.id, channel.id)
            if group_config:
                success = await self.refresh_group_index(interaction.guild.id, channel.id)
                if success:
                    await interaction.followup.send(
                        f"✅ Refreshed group index for **{channel.name}**",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ Failed to refresh group index for **{channel.name}**",
                        ephemeral=True
                    )
                return
            # If not a group index, check if it's a forum (regular index)
            elif isinstance(channel, discord.ForumChannel):
                forum = channel
            else:
                await interaction.followup.send(
                    f"❌ No index configured for **{channel.name}**",
                    ephemeral=True
                )
                return
        
        if forum:
            # Refresh specific forum (regular index)
            config = self.config.get_index(interaction.guild.id, forum.id)
            if not config:
                await interaction.followup.send(
                    f"❌ No index configured for **{forum.name}**",
                    ephemeral=True
                )
                return
            
            success = await self.refresh_index(interaction.guild.id, forum.id)
            if success:
                await interaction.followup.send(
                    f"✅ Refreshed index for **{forum.name}**",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to refresh index for **{forum.name}**",
                    ephemeral=True
                )
        else:
            # Refresh all indexes in this guild (both regular and group)
            indexes = self.config.get_indexes(interaction.guild.id)
            group_indexes = self.config.get_group_indexes(interaction.guild.id)
            
            if not indexes and not group_indexes:
                await interaction.followup.send(
                    "❌ No indexes configured for this guild",
                    ephemeral=True
                )
                return
            
            refreshed = []
            failed = []
            
            # Refresh regular indexes
            for key, config in indexes.items():
                forum_id = config["forum_id"]
                success = await self.refresh_index(interaction.guild.id, forum_id)
                if success:
                    refreshed.append(config["index_name"])
                else:
                    failed.append(config["index_name"])
            
            # Refresh group indexes
            for key, config in group_indexes.items():
                target_channel_id = config["target_channel_id"]
                success = await self.refresh_group_index(interaction.guild.id, target_channel_id)
                if success:
                    refreshed.append(f"{config['group_index_name']} (group)")
                else:
                    failed.append(f"{config['group_index_name']} (group)")
            
            result = []
            if refreshed:
                result.append(f"✅ Refreshed: {', '.join(refreshed)}")
            if failed:
                result.append(f"❌ Failed: {', '.join(failed)}")
            
            await interaction.followup.send("\n".join(result), ephemeral=True)
    
    @index_group.command(name="list", description="List all configured indexes")
    @app_commands.default_permissions(administrator=True)
    async def index_list(self, interaction: discord.Interaction):
        """List all configured indexes."""
        await interaction.response.defer(ephemeral=True)
        
        indexes = self.config.get_indexes(interaction.guild.id)
        group_indexes = self.config.get_group_indexes(interaction.guild.id)
        
        if not indexes and not group_indexes:
            await interaction.followup.send(
                "No indexes configured for this guild.",
                ephemeral=True
            )
            return
        
        lines = []
        # Regular indexes
        for key, config in indexes.items():
            forum = interaction.guild.get_channel(config["forum_id"])
            forum_name = forum.name if forum else f"Unknown ({config['forum_id']})"
            sort_info = ""
            if config.get("sort_by_title_pattern"):
                pattern = config.get("title_grouping_pattern", "")
                sort_info = f" (title-pattern: {pattern})" if pattern else " (title-pattern)"
            elif config.get("sort_by_tags"):
                sort_info = " (tag-sorted)"
            lines.append(f"• **{config['index_name']}** — {forum_name}{sort_info}")
        
        # Group indexes
        for key, config in group_indexes.items():
            target_channel = interaction.guild.get_channel(config["target_channel_id"])
            channel_name = target_channel.name if target_channel else f"Unknown ({config['target_channel_id']})"
            source_count = len(config.get("source_forum_ids", []))
            sort_info = ""
            if config.get("sort_by_title_pattern"):
                pattern = config.get("title_grouping_pattern", "")
                sort_info = f" (title-pattern: {pattern})" if pattern else " (title-pattern)"
            elif config.get("sort_by_tags"):
                sort_info = " (tag-sorted)"
            lines.append(f"• **{config['group_index_name']}** (group) — {channel_name} ({source_count} source forum{'s' if source_count != 1 else ''}){sort_info}")
        
        await interaction.followup.send(
            f"**Configured Indexes:**\n" + "\n".join(lines),
            ephemeral=True
        )
    
    @index_group.command(name="remove", description="Remove an index configuration")
    @app_commands.describe(
        forum="The forum channel to remove from indexing (for regular indexes)",
        channel="The channel to remove from indexing (for group indexes, use this instead of forum)"
    )
    @app_commands.default_permissions(administrator=True)
    async def index_remove(
        self,
        interaction: discord.Interaction,
        forum: Optional[discord.ForumChannel] = None,
        channel: Optional[Union[discord.TextChannel, discord.ForumChannel]] = None
    ):
        """Remove an index configuration."""
        await interaction.response.defer(ephemeral=True)
        
        # Check if channel is provided (for group indexes)
        if channel:
            # Try to remove as group index first
            group_config = self.config.get_group_index(interaction.guild.id, channel.id)
            if group_config:
                self.config.remove_group_index(interaction.guild.id, channel.id)
                
                # Clear cache
                group_key = self._get_group_index_key(interaction.guild.id, channel.id)
                self.group_index_thread_ids.pop(group_key, None)
                
                await interaction.followup.send(
                    f"✅ Removed group index configuration for **{channel.name}**",
                    ephemeral=True
                )
                return
            # If not a group index, check if it's a forum (regular index)
            elif isinstance(channel, discord.ForumChannel):
                forum = channel
            else:
                await interaction.followup.send(
                    f"❌ No index configured for **{channel.name}**",
                    ephemeral=True
                )
                return
        
        if not forum:
            await interaction.followup.send(
                "❌ Please provide either a forum or channel parameter.",
                ephemeral=True
            )
            return
        
        # Remove regular index
        config = self.config.get_index(interaction.guild.id, forum.id)
        if not config:
            await interaction.followup.send(
                f"❌ No index configured for **{forum.name}**",
                ephemeral=True
            )
            return
        
        self.config.remove_index(interaction.guild.id, forum.id)
        
        # Clear cache
        index_key = self._get_index_key(interaction.guild.id, forum.id)
        self.index_thread_ids.pop(index_key, None)
        self.last_chunks.pop(index_key, None)
        
        await interaction.followup.send(
            f"✅ Removed index configuration for **{forum.name}**",
            ephemeral=True
        )
    
    @index_group.command(name="edit", description="Edit an existing index configuration")
    @app_commands.describe(
        forum="The forum channel whose index configuration to edit (for regular indexes)",
        channel="The channel whose index configuration to edit (for group indexes, use this instead of forum)"
    )
    @app_commands.default_permissions(administrator=True)
    async def index_edit(
        self,
        interaction: discord.Interaction,
        forum: Optional[discord.ForumChannel] = None,
        channel: Optional[Union[discord.TextChannel, discord.ForumChannel]] = None
    ):
        """Edit an index configuration using a modal."""
        # Check if channel is provided (for group indexes)
        if channel:
            # Try to edit as group index first
            group_config = self.config.get_group_index(interaction.guild.id, channel.id)
            if group_config:
                # Create and show the group index edit modal
                modal = GroupIndexEditModal(self, group_config)
                await interaction.response.send_modal(modal)
                return
            # If not a group index, check if it's a forum (regular index)
            elif isinstance(channel, discord.ForumChannel):
                forum = channel
            else:
                await interaction.response.send_message(
                    f"❌ No index configured for **{channel.name}**. Use `/index add` or `/index group` to create one.",
                    ephemeral=True
                )
                return
        
        if not forum:
            await interaction.response.send_message(
                "❌ Please provide either a forum or channel parameter.",
                ephemeral=True
            )
            return
        
        # Edit regular index
        config = self.config.get_index(interaction.guild.id, forum.id)
        if not config:
            await interaction.response.send_message(
                f"❌ No index configured for **{forum.name}**. Use `/index add` to create one.",
                ephemeral=True
            )
            return
        
        # Create and show the edit modal with existing values
        modal = IndexEditModal(self, config)
        await interaction.response.send_modal(modal)
    
    @index_group.command(name="group", description="Create a group index that combines multiple forums")
    @app_commands.default_permissions(administrator=True)
    async def index_group_create(self, interaction: discord.Interaction):
        """Start the group index creation wizard."""
        # Create and show the wizard view with channel selectors
        view = GroupIndexWizardView(self, interaction.guild)
        await interaction.response.send_message(
            "📚 **Group Index Creation Wizard**\n\n"
            "**Step 1 of 4:** Select the target channel where the index will be created.\n"
            "Then fill out the form below and click **Continue**.",
            view=view,
            ephemeral=True
        )
        # Store reference to the message
        view.original_message = await interaction.original_response()


class GroupIndexWizardView(discord.ui.View):
    """Interactive view for creating group indexes step by step."""
    
    def __init__(self, cog: IndexManager, guild: discord.Guild):
        super().__init__(timeout=600)  # 10 minute timeout
        self.cog = cog
        self.guild = guild
        self.step = 1  # Start at step 1
        self.config_data = {}
        self.original_message = None  # Store reference to original message
        self._setup_step_1()
    
    def _setup_step_1(self):
        """Setup Step 1: Target channel and name."""
        self.clear_items()
        
        # Group Index Name input (use modal for text input)
        name_button = discord.ui.Button(label="Enter Group Index Name", style=discord.ButtonStyle.primary)
        name_button.callback = self._open_name_modal
        self.add_item(name_button)
        
        # Target Channel select (text or forum channels only)
        target_select = discord.ui.ChannelSelect(
            placeholder="Select target channel (text or forum)...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.forum],
            max_values=1,
            min_values=1
        )
        target_select.callback = self._on_target_channel_select
        self.add_item(target_select)
    
    async def _open_name_modal(self, interaction: discord.Interaction):
        """Open modal for group index name."""
        modal = GroupIndexNameModal(self)
        await interaction.response.send_modal(modal)
    
    async def _on_target_channel_select(self, interaction: discord.Interaction):
        """Handle target channel selection."""
        # ChannelSelect returns channel IDs in interaction.data['values']
        if not interaction.data.get('values'):
            await interaction.response.send_message(
                "❌ No channel selected.",
                ephemeral=True
            )
            return
        
        channel_id = int(interaction.data['values'][0])
        target_channel = self.guild.get_channel(channel_id)
        
        if not target_channel or not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
            await interaction.response.send_message(
                "❌ Please select a text channel or forum channel.",
                ephemeral=True
            )
            return
        
        self.config_data["target_channel_id"] = target_channel.id
        
        # Check if name is set
        if "group_index_name" not in self.config_data:
            await interaction.response.send_message(
                f"✅ Target channel selected: {target_channel.mention}\n\n"
                "Now click **Enter Group Index Name** to continue.",
                ephemeral=True
            )
        else:
            # Both set, move to step 2
            await interaction.response.defer()
            await self._move_to_step_2(interaction)
    
    async def _move_to_step_2(self, interaction: discord.Interaction):
        """Move to step 2: Source forums."""
        # If interaction is already deferred, we can edit directly
        # Otherwise, we need to defer first
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        self.step = 2
        self._setup_step_2()
        
        target_channel = self.guild.get_channel(self.config_data["target_channel_id"])
        content = (
            "📚 **Group Index Creation Wizard**\n\n"
            "✅ **Step 1 complete!**\n"
            f"- Name: **{self.config_data['group_index_name']}**\n"
            f"- Target: {target_channel.mention if target_channel else 'Unknown'}\n\n"
            "**Step 2 of 4:** Select the source forum channels to index.\n"
            "You can select multiple forums at once, or add them one by one."
        )
        # Edit the original message if we have it
        if self.original_message:
            await self.original_message.edit(content=content, view=self)
        else:
            # Fallback: try to edit original response
            try:
                await interaction.edit_original_response(content=content, view=self)
            except:
                # If that fails, send a new message
                await interaction.followup.send(content, view=self, ephemeral=True)
    
    def _setup_step_2(self):
        """Setup Step 2: Source forums."""
        self.clear_items()
        
        # Source Forum select (forum channels only, multiple selection)
        forum_select = discord.ui.ChannelSelect(
            placeholder="Select source forum channels (hold Ctrl/Cmd to select multiple)...",
            channel_types=[discord.ChannelType.forum],
            max_values=25,  # Discord limit
            min_values=1,
            row=0
        )
        forum_select.callback = self._on_source_forums_select
        self.add_item(forum_select)
        
        # Continue button (user can add more forums if needed)
        continue_button = discord.ui.Button(label="Continue to Step 3", style=discord.ButtonStyle.primary)
        continue_button.callback = self._continue_to_step_3
        self.add_item(continue_button)
    
    async def _on_source_forums_select(self, interaction: discord.Interaction):
        """Handle source forum selection."""
        # ChannelSelect returns channel IDs in interaction.data['values']
        if not interaction.data.get('values'):
            await interaction.response.send_message(
                "❌ No forums selected.",
                ephemeral=True
            )
            return
        
        # Get channel IDs and fetch channels
        channel_ids = [int(ch_id) for ch_id in interaction.data['values']]
        selected_forums = []
        
        for channel_id in channel_ids:
            channel = self.guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.ForumChannel):
                selected_forums.append(channel)
        
        if not selected_forums:
            await interaction.response.send_message(
                "❌ Please select forum channels only.",
                ephemeral=True
            )
            return
        
        # Add to or update source forums list
        if "source_forum_ids" not in self.config_data:
            self.config_data["source_forum_ids"] = []
        
        # Add new forums (avoid duplicates)
        existing_ids = set(self.config_data["source_forum_ids"])
        for forum in selected_forums:
            if forum.id not in existing_ids:
                self.config_data["source_forum_ids"].append(forum.id)
        
        forum_names = [f.mention for f in selected_forums]
        count = len(self.config_data["source_forum_ids"])
        
        await interaction.response.send_message(
            f"✅ Added {len(selected_forums)} forum(s). Total selected: **{count}**\n"
            f"Forums: {', '.join(forum_names[:5])}"
            + (f" and {count - 5} more..." if count > 5 else ""),
            ephemeral=True
        )
    
    async def _continue_to_step_3(self, interaction: discord.Interaction):
        """Move to step 3: Sorting options."""
        if "source_forum_ids" not in self.config_data or not self.config_data["source_forum_ids"]:
            await interaction.response.send_message(
                "❌ Please select at least one source forum channel first.",
                ephemeral=True
            )
            return
        
        # Defer the interaction first
        await interaction.response.defer(ephemeral=True)
        
        self.step = 3
        self._setup_step_3()
        
        source_count = len(self.config_data["source_forum_ids"])
        content = (
            "📚 **Group Index Creation Wizard**\n\n"
            "✅ **Step 2 complete!**\n"
            f"- Selected **{source_count}** source forum(s)\n\n"
            "**Step 3 of 4:** Configure sorting options.\n"
            "Click the buttons below to configure how threads will be grouped and sorted."
        )
        # Edit the original message if we have it
        if self.original_message:
            await self.original_message.edit(content=content, view=self)
        else:
            # Fallback: try to edit original response
            try:
                await interaction.edit_original_response(content=content, view=self)
            except:
                # If that fails, send a new message
                await interaction.followup.send(content, view=self, ephemeral=True)
    
    def _setup_step_3(self):
        """Setup Step 3: Sorting options."""
        self.clear_items()
        
        # Sorting option buttons
        sort_by_tags_btn = discord.ui.Button(label="Sort by Tags", style=discord.ButtonStyle.secondary)
        sort_by_tags_btn.callback = self._open_sorting_modal
        self.add_item(sort_by_tags_btn)
        
        # Title Pattern Select dropdown with descriptions
        pattern_select = discord.ui.Select(
            placeholder="Select Title Pattern Sorting Option...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Date Number",
                    value="date-number",
                    description="Group by date number (e.g., '582' from 'SD1-582' or 'WD2-582')",
                    emoji="🔢"
                ),
                discord.SelectOption(
                    label="Date Suffix (Full)",
                    value="date-suffix",
                    description="Group by full date code (e.g., 'SD1-582' and 'WD2-582' are separate)",
                    emoji="📅"
                ),
                discord.SelectOption(
                    label="After Last Dash",
                    value="after-",
                    description="Group by text after the last dash in title",
                    emoji="➡️"
                ),
                discord.SelectOption(
                    label="Before First Dash",
                    value="before-",
                    description="Group by text before the first dash in title",
                    emoji="⬅️"
                ),
                discord.SelectOption(
                    label="Custom Regex Pattern",
                    value="__custom__",
                    description="Enter a custom regex pattern (e.g., '([A-Z]+\\d+)-\\d+' to match 'SD1' from 'SD1-582')",
                    emoji="🔧"
                )
            ],
            row=1
        )
        pattern_select.callback = self._on_pattern_select
        self.add_item(pattern_select)
        
        # Default values if not set
        self.config_data.setdefault("sort_by_tags", False)
        self.config_data.setdefault("sort_by_title_pattern", False)
        self.config_data.setdefault("preferred_tags", None)
        self.config_data.setdefault("priority_tag", None)
        self.config_data.setdefault("title_grouping_pattern", None)
        
        # Priority tag button (optional, can be set after pattern selection)
        priority_tag_btn = discord.ui.Button(label="Set Priority Tag (Optional)", style=discord.ButtonStyle.secondary)
        priority_tag_btn.callback = self._open_priority_tag_modal
        self.add_item(priority_tag_btn)
        
        # Continue button
        continue_button = discord.ui.Button(label="Continue to Final Step", style=discord.ButtonStyle.primary)
        continue_button.callback = self._continue_to_final_step
        self.add_item(continue_button)
    
    async def _open_sorting_modal(self, interaction: discord.Interaction):
        """Open modal for tag sorting configuration."""
        modal = GroupIndexSortingModal(self)
        await interaction.response.send_modal(modal)
    
    async def _on_pattern_select(self, interaction: discord.Interaction):
        """Handle title pattern selection."""
        selected_value = interaction.data['values'][0] if interaction.data.get('values') else None
        
        if selected_value == "__custom__":
            # Open modal for custom regex input
            modal = GroupIndexPatternModal(self)
            await interaction.response.send_modal(modal)
        else:
            # Use the selected built-in pattern
            self.config_data["sort_by_tags"] = False
            self.config_data["sort_by_title_pattern"] = True
            self.config_data["title_grouping_pattern"] = selected_value
            
            pattern_names = {
                "date-number": "Date Number",
                "date-suffix": "Date Suffix (Full)",
                "after-": "After Last Dash",
                "before-": "Before First Dash"
            }
            pattern_name = pattern_names.get(selected_value, selected_value)
            
            await interaction.response.send_message(
                f"✅ Title pattern sorting configured!\n"
                f"- Pattern: **{pattern_name}**\n"
                f"- Value: `{selected_value}`\n\n"
                f"You can also set a priority tag using the button below if needed.",
                ephemeral=True
            )
    
    async def _open_priority_tag_modal(self, interaction: discord.Interaction):
        """Open modal for priority tag configuration."""
        modal = GroupIndexPriorityTagModal(self)
        await interaction.response.send_modal(modal)
    
    async def _continue_to_final_step(self, interaction: discord.Interaction):
        """Move to final step based on target channel type."""
        target_channel_id = self.config_data.get("target_channel_id")
        target_channel = self.guild.get_channel(target_channel_id) if target_channel_id else None
        
        # Defer the interaction first
        await interaction.response.defer(ephemeral=True)
        
        if isinstance(target_channel, discord.ForumChannel):
            # Need thread sorting options
            self.step = 4
            self._setup_step_4()
            content = (
                "📚 **Group Index Creation Wizard**\n\n"
                "✅ **Step 3 complete!**\n\n"
                "**Step 4 of 4:** Configure thread sorting (forum channels only).\n"
                "Since the target is a forum, configure how index threads should be sorted."
            )
            # Edit the original message if we have it
            if self.original_message:
                await self.original_message.edit(content=content, view=self)
            else:
                # Fallback: try to edit original response
                try:
                    await interaction.edit_original_response(content=content, view=self)
                except:
                    # If that fails, send a new message
                    await interaction.followup.send(content, view=self, ephemeral=True)
        else:
            # Finalize for normal channels
            await interaction.response.defer(ephemeral=True)
            await self._finalize(interaction)
    
    def _setup_step_4(self):
        """Setup Step 4: Thread sorting (forum only)."""
        self.clear_items()
        
        # Thread sorting configuration button
        thread_sort_btn = discord.ui.Button(label="Configure Thread Sorting", style=discord.ButtonStyle.secondary)
        thread_sort_btn.callback = self._open_thread_sort_modal
        self.add_item(thread_sort_btn)
        
        # Finalize button
        finalize_button = discord.ui.Button(label="Create Group Index", style=discord.ButtonStyle.success)
        finalize_button.callback = self._finalize_from_view
        self.add_item(finalize_button)
    
    async def _open_thread_sort_modal(self, interaction: discord.Interaction):
        """Open modal for thread sorting configuration."""
        modal = GroupIndexThreadSortModal(self)
        await interaction.response.send_modal(modal)
    
    async def _finalize_from_view(self, interaction: discord.Interaction):
        """Finalize from view button."""
        await interaction.response.defer(ephemeral=True)
        await self._finalize(interaction)
    
    async def _finalize(self, interaction: discord.Interaction):
        """Finalize the group index creation."""
        config = self.config_data
        
        # Add default values
        if not config.get("intro_text"):
            config["intro_text"] = f"📚 Group Index: {config['group_index_name']}"
        config.setdefault("use_character_sorting", False)
        config.setdefault("thread_sort_by", "creation")
        
        # Save configuration
        self.cog.config.add_group_index(
            guild_id=self.guild.id,
            target_channel_id=config["target_channel_id"],
            group_index_name=config["group_index_name"],
            source_forum_ids=config["source_forum_ids"],
            sort_by_tags=config.get("sort_by_tags", False),
            preferred_tags=config.get("preferred_tags"),
            intro_text=config["intro_text"],
            priority_tag=config.get("priority_tag"),
            sort_by_title_pattern=config.get("sort_by_title_pattern", False),
            title_grouping_pattern=config.get("title_grouping_pattern"),
            thread_sort_by=config.get("thread_sort_by", "creation"),
            thread_sort_tag=config.get("thread_sort_tag")
        )
        
        # Build success message
        warnings = config.get("_warnings", [])
        success_msg = f"✅ Group index **{config['group_index_name']}** created successfully!"
        
        if warnings:
            warnings_text = "\n".join(warnings[:5])  # Limit to 5 warnings
            if len(warnings) > 5:
                warnings_text += f"\n... and {len(warnings) - 5} more warning(s)"
            success_msg = f"{warnings_text}\n\n{success_msg}"
        
        # Immediately build the index
        target_channel = self.guild.get_channel(config["target_channel_id"])
        if target_channel:
            try:
                await self.cog.build_group_index(self.guild, target_channel, config)
                target_mention = target_channel.mention if hasattr(target_channel, 'mention') else f"channel {target_channel.name}"
                success_msg += f"\n\nThe index has been created in {target_mention}."
            except Exception as e:
                success_msg += f"\n\n⚠️ Warning: Error building index: {e}"
        
        # Use followup if deferred, otherwise edit message
        if interaction.response.is_done():
            await interaction.followup.send(success_msg, ephemeral=True)
        else:
            await interaction.response.edit_message(content=success_msg, view=None)


class GroupIndexNameModal(discord.ui.Modal, title="Group Index Name"):
    """Modal for entering group index name."""
    
    def __init__(self, wizard_view: GroupIndexWizardView):
        super().__init__()
        self.wizard_view = wizard_view
        
        self.group_name_input = discord.ui.TextInput(
            label="Group Index Name",
            placeholder="e.g., All Character Threads, Combined Resources",
            required=True,
            max_length=100
        )
        
        self.add_item(self.group_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_view.config_data["group_index_name"] = self.group_name_input.value
        
        # Check if target channel is also set
        if "target_channel_id" in self.wizard_view.config_data:
            # Both set, move to step 2
            target_channel = self.wizard_view.guild.get_channel(self.wizard_view.config_data["target_channel_id"])
            await interaction.response.send_message(
                f"✅ Group index name set: **{self.group_name_input.value}**\n\n"
                "Now select the target channel above, or continue if already selected.",
                ephemeral=True
            )
            
            # Update main message if both are set
            if target_channel:
                await self.wizard_view._move_to_step_2(interaction)
        else:
            await interaction.response.send_message(
                f"✅ Group index name set: **{self.group_name_input.value}**\n\n"
                "Now select the target channel above to continue.",
                ephemeral=True
            )


class GroupIndexSortingModal(discord.ui.Modal, title="Tag Sorting Configuration"):
    """Modal for configuring tag-based sorting."""
    
    def __init__(self, wizard_view: GroupIndexWizardView):
        super().__init__()
        self.wizard_view = wizard_view
        
        preferred_tags = ", ".join(self.wizard_view.config_data.get("preferred_tags", [])) if self.wizard_view.config_data.get("preferred_tags") else ""
        priority_tag = self.wizard_view.config_data.get("priority_tag", "") or ""
        
        self.preferred_tags_input = discord.ui.TextInput(
            label="Preferred Tags (comma-separated, optional)",
            placeholder="e.g., Night Court, Day Court, Dawn Court",
            default=preferred_tags,
            required=False,
            max_length=500,
            style=discord.TextStyle.long
        )
        
        self.priority_tag_input = discord.ui.TextInput(
            label="Priority Tag (optional)",
            placeholder="Tag name for entries to show at top with emoji",
            default=priority_tag,
            required=False,
            max_length=100
        )
        
        self.add_item(self.preferred_tags_input)
        self.add_item(self.priority_tag_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Parse preferred tags
        preferred_tags_list = None
        if self.preferred_tags_input.value.strip():
            preferred_tags_list = [tag.strip() for tag in self.preferred_tags_input.value.split(",") if tag.strip()]
        
        self.wizard_view.config_data["sort_by_tags"] = True
        self.wizard_view.config_data["sort_by_title_pattern"] = False
        self.wizard_view.config_data["preferred_tags"] = preferred_tags_list
        self.wizard_view.config_data["priority_tag"] = self.priority_tag_input.value.strip() or None
        
        await interaction.response.send_message(
            f"✅ Tag sorting configured!\n"
            f"- Preferred tags: {', '.join(preferred_tags_list) if preferred_tags_list else 'All tags'}\n"
            f"- Priority tag: {self.wizard_view.config_data['priority_tag'] or 'None'}",
            ephemeral=True
        )


class GroupIndexPatternModal(discord.ui.Modal, title="Custom Regex Pattern"):
    """Modal for entering custom regex pattern."""
    
    def __init__(self, wizard_view: GroupIndexWizardView):
        super().__init__()
        self.wizard_view = wizard_view
        
        title_grouping_pattern = self.wizard_view.config_data.get("title_grouping_pattern", "") or ""
        
        self.title_grouping_pattern_input = discord.ui.TextInput(
            label="Custom Regex Pattern",
            placeholder="e.g., '([A-Z]+\\d+)-\\d+' to match 'SD1' from 'SD1-582'",
            default=title_grouping_pattern if title_grouping_pattern not in ["date-number", "date-suffix", "after-", "before-"] else "",
            required=True,
            max_length=200
        )
        
        self.add_item(self.title_grouping_pattern_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        pattern = self.title_grouping_pattern_input.value.strip()
        if not pattern:
            await interaction.response.send_message(
                "❌ Regex pattern is required.",
                ephemeral=True
            )
            return
        
        # Validate regex pattern
        try:
            re.compile(pattern)
        except re.error as e:
            await interaction.response.send_message(
                f"❌ Invalid regex pattern: {str(e)}\n\n"
                f"Please check your regex syntax and try again.",
                ephemeral=True
            )
            return
        
        self.wizard_view.config_data["sort_by_tags"] = False
        self.wizard_view.config_data["sort_by_title_pattern"] = True
        self.wizard_view.config_data["title_grouping_pattern"] = pattern
        
        await interaction.response.send_message(
            f"✅ Custom regex pattern configured!\n"
            f"- Pattern: `{pattern}`\n\n"
            f"You can set a priority tag using the button below if needed.",
            ephemeral=True
        )


class GroupIndexPriorityTagModal(discord.ui.Modal, title="Priority Tag Configuration"):
    """Modal for configuring priority tag (optional)."""
    
    def __init__(self, wizard_view: GroupIndexWizardView):
        super().__init__()
        self.wizard_view = wizard_view
        
        priority_tag = self.wizard_view.config_data.get("priority_tag", "") or ""
        
        self.priority_tag_input = discord.ui.TextInput(
            label="Priority Tag (optional)",
            placeholder="Tag name for entries to show at top with emoji",
            default=priority_tag,
            required=False,
            max_length=100
        )
        
        self.add_item(self.priority_tag_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        priority_tag = self.priority_tag_input.value.strip() or None
        self.wizard_view.config_data["priority_tag"] = priority_tag
        
        await interaction.response.send_message(
            f"✅ Priority tag {'set' if priority_tag else 'cleared'}!\n"
            f"- Priority tag: **{priority_tag or 'None'}**",
            ephemeral=True
        )


class GroupIndexThreadSortModal(discord.ui.Modal, title="Thread Sorting Configuration"):
    """Modal for configuring thread sorting (forum channels only)."""
    
    def __init__(self, wizard_view: GroupIndexWizardView):
        super().__init__()
        self.wizard_view = wizard_view
        
        thread_sort_by = self.wizard_view.config_data.get("thread_sort_by", "creation")
        thread_sort_tag = self.wizard_view.config_data.get("thread_sort_tag", "") or ""
        intro_text = self.wizard_view.config_data.get("intro_text", "") or ""
        
        self.thread_sort_by_input = discord.ui.TextInput(
            label="Sort Threads By",
            placeholder="'creation' or 'tag'",
            default=thread_sort_by,
            required=False,
            max_length=10
        )
        
        self.thread_sort_tag_input = discord.ui.TextInput(
            label="Sort Tag (if sorting by tag)",
            placeholder="Tag name to sort threads by (optional)",
            default=thread_sort_tag,
            required=False,
            max_length=100
        )
        
        self.intro_text_input = discord.ui.TextInput(
            label="Intro Text (optional)",
            placeholder="Intro text for group index",
            default=intro_text,
            required=False,
            max_length=500,
            style=discord.TextStyle.long
        )
        
        self.add_item(self.thread_sort_by_input)
        self.add_item(self.thread_sort_tag_input)
        self.add_item(self.intro_text_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        thread_sort_by = self.thread_sort_by_input.value.strip().lower() or "creation"
        if thread_sort_by not in ("creation", "tag"):
            thread_sort_by = "creation"
        
        self.wizard_view.config_data["thread_sort_by"] = thread_sort_by
        self.wizard_view.config_data["thread_sort_tag"] = self.thread_sort_tag_input.value.strip() or None
        self.wizard_view.config_data["intro_text"] = self.intro_text_input.value.strip() or None
        
        await interaction.response.send_message(
            f"✅ Thread sorting configured!\n"
            f"- Sort by: {thread_sort_by}\n"
            f"- Sort tag: {self.wizard_view.config_data['thread_sort_tag'] or 'None'}\n"
            f"- Intro text: {'Set' if self.wizard_view.config_data['intro_text'] else 'Default'}",
            ephemeral=True
        )


class IndexEditModal(discord.ui.Modal, title="Edit Index Configuration"):
    """Modal for editing index configuration."""
    
    def __init__(self, cog: IndexManager, config: dict):
        super().__init__()
        self.cog = cog
        self.config = config
        self.forum_id = config["forum_id"]
        self.guild_id = config["guild_id"]
        
        # Get existing values with defaults
        index_name = config.get("index_name", "")
        sort_by_tags = str(config.get("sort_by_tags", False)).lower()
        sort_by_title_pattern = str(config.get("sort_by_title_pattern", False)).lower()
        preferred_tags = ", ".join(config.get("preferred_tags", [])) if config.get("preferred_tags") else ""
        priority_tag = config.get("priority_tag", "") or ""
        index_thread_name = config.get("index_thread_name", "") or ""
        intro_text = config.get("intro_text", "") or ""
        thumb_url = config.get("thumb_url", "") or ""
        use_character_sorting = str(config.get("use_character_sorting", False)).lower()
        title_grouping_pattern = config.get("title_grouping_pattern", "") or ""
        
        # Field 1: Index Name (required)
        self.index_name_input = discord.ui.TextInput(
            label="Index Name",
            placeholder="e.g., Characters, Resources",
            default=index_name,
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        
        # Field 2: Sort By Tags (true/false)
        self.sort_by_tags_input = discord.ui.TextInput(
            label="Sort By Tags",
            placeholder="Enter 'true' or 'false'",
            default=sort_by_tags,
            required=False,
            max_length=5,
            style=discord.TextStyle.short
        )
        
        # Field 3: Sort By Title Pattern (true/false)
        self.sort_by_title_pattern_input = discord.ui.TextInput(
            label="Sort By Title Pattern",
            placeholder="Enter 'true' or 'false' (alternative to tags)",
            default=sort_by_title_pattern,
            required=False,
            max_length=5,
            style=discord.TextStyle.short
        )
        
        # Field 4: Title Grouping Pattern
        pattern_placeholder = "'date-number', 'date-suffix', 'after-', 'before-', or regex"
        self.title_grouping_pattern_input = discord.ui.TextInput(
            label="Title Grouping Pattern",
            placeholder=pattern_placeholder,
            default=title_grouping_pattern,
            required=False,
            max_length=200,
            style=discord.TextStyle.short
        )
        
        # Field 5: Preferred Tags (comma-separated)
        self.preferred_tags_input = discord.ui.TextInput(
            label="Preferred Tags (comma-separated)",
            placeholder="e.g., Night Court, Day Court, Dawn Court",
            default=preferred_tags,
            required=False,
            max_length=500,
            style=discord.TextStyle.long
        )
        
        # Additional fields - Note: Discord modals have a 5-field limit, so these are in a second modal if needed
        # For now, we'll use existing modal structure and add priority_tag and index_thread_name handling
        
        self.add_item(self.index_name_input)
        self.add_item(self.sort_by_tags_input)
        self.add_item(self.sort_by_title_pattern_input)
        self.add_item(self.title_grouping_pattern_input)
        self.add_item(self.preferred_tags_input)
        
        # Store other fields that aren't in the modal (we'll preserve them)
        self._priority_tag = priority_tag
        self._index_thread_name = index_thread_name
        self._intro_text = intro_text
        self._thumb_url = thumb_url
        self._use_character_sorting = use_character_sorting
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Parse boolean fields
        sort_by_tags = self.config.get("sort_by_tags", False)  # Default to existing
        sort_by_tags_str = self.sort_by_tags_input.value.strip().lower()
        if sort_by_tags_str in ("true", "yes", "1", "on"):
            sort_by_tags = True
        elif sort_by_tags_str in ("false", "no", "0", "off"):
            sort_by_tags = False
        
        sort_by_title_pattern = self.config.get("sort_by_title_pattern", False)  # Default to existing
        sort_by_title_pattern_str = self.sort_by_title_pattern_input.value.strip().lower()
        if sort_by_title_pattern_str in ("true", "yes", "1", "on"):
            sort_by_title_pattern = True
        elif sort_by_title_pattern_str in ("false", "no", "0", "off"):
            sort_by_title_pattern = False
        
        # Get title grouping pattern
        title_grouping_pattern = self.title_grouping_pattern_input.value.strip() or None
        
        # Validate title pattern if provided
        if sort_by_title_pattern and not title_grouping_pattern:
            await interaction.followup.send(
                "❌ `title_grouping_pattern` is required when `sort_by_title_pattern` is true.",
                ephemeral=True
            )
            return
        
        # Parse preferred tags
        preferred_tags_str = self.preferred_tags_input.value.strip()
        preferred_tags_list = None
        if preferred_tags_str:
            preferred_tags_list = [tag.strip() for tag in preferred_tags_str.split(",") if tag.strip()]
        
        # Get other values
        index_name = self.index_name_input.value.strip()
        
        # Preserve existing values for fields not in modal
        intro_text = self._intro_text
        thumb_url = self._thumb_url
        use_character_sorting = self._use_character_sorting
        priority_tag = self._priority_tag or None
        index_thread_name = self._index_thread_name or None
        
        # Update index configuration
        self.cog.config.add_index(
            guild_id=self.guild_id,
            forum_id=self.forum_id,
            index_name=index_name,
            sort_by_tags=sort_by_tags,
            preferred_tags=preferred_tags_list,
            index_thread_name=index_thread_name,
            intro_text=intro_text,
            thumb_url=thumb_url,
            use_character_sorting=use_character_sorting,
            priority_tag=priority_tag,
            sort_by_title_pattern=sort_by_title_pattern,
            title_grouping_pattern=title_grouping_pattern
        )
        
        # Refresh the index
        await self.cog.refresh_index(self.guild_id, self.forum_id)
        
        # Build response message
        tag_info = ""
        if sort_by_tags:
            if preferred_tags_list:
                tag_info = f" (sorting by tags: {', '.join(preferred_tags_list)})"
            else:
                tag_info = " (sorting by all tags)"
        elif sort_by_title_pattern:
            tag_info = f" (sorting by title pattern: {title_grouping_pattern})"
        
        priority_info = ""
        if priority_tag:
            priority_info = f" (priority tag: {priority_tag})"
        
        guild = self.cog.bot.get_guild(self.guild_id)
        forum = guild.get_channel(self.forum_id) if guild else None
        forum_name = forum.name if forum else "Unknown"
        
        await interaction.followup.send(
            f"✅ Updated index configuration for **{forum_name}** ({index_name}){tag_info}{priority_info}",
            ephemeral=True
        )


class GroupIndexEditModal(discord.ui.Modal, title="Edit Group Index Configuration"):
    """Modal for editing group index configuration."""
    
    def __init__(self, cog: IndexManager, config: dict):
        super().__init__()
        self.cog = cog
        self.config = config
        self.target_channel_id = config["target_channel_id"]
        self.guild_id = config["guild_id"]
        
        # Get existing values with defaults
        group_index_name = config.get("group_index_name", "")
        sort_by_tags = str(config.get("sort_by_tags", False)).lower()
        sort_by_title_pattern = str(config.get("sort_by_title_pattern", False)).lower()
        preferred_tags = ", ".join(config.get("preferred_tags", [])) if config.get("preferred_tags") else ""
        priority_tag = config.get("priority_tag", "") or ""
        intro_text = config.get("intro_text", "") or ""
        title_grouping_pattern = config.get("title_grouping_pattern", "") or ""
        thread_sort_by = config.get("thread_sort_by", "creation")
        thread_sort_tag = config.get("thread_sort_tag", "") or ""
        
        # Field 1: Group Index Name (required)
        self.group_index_name_input = discord.ui.TextInput(
            label="Group Index Name",
            placeholder="e.g., All Character Threads, Combined Resources",
            default=group_index_name,
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        
        # Field 2: Sort By Tags (true/false)
        self.sort_by_tags_input = discord.ui.TextInput(
            label="Sort By Tags",
            placeholder="Enter 'true' or 'false'",
            default=sort_by_tags,
            required=False,
            max_length=5,
            style=discord.TextStyle.short
        )
        
        # Field 3: Sort By Title Pattern (true/false)
        self.sort_by_title_pattern_input = discord.ui.TextInput(
            label="Sort By Title Pattern",
            placeholder="Enter 'true' or 'false' (alternative to tags)",
            default=sort_by_title_pattern,
            required=False,
            max_length=5,
            style=discord.TextStyle.short
        )
        
        # Field 4: Title Grouping Pattern
        pattern_placeholder = "'date-number', 'date-suffix', 'after-', 'before-', or regex"
        self.title_grouping_pattern_input = discord.ui.TextInput(
            label="Title Grouping Pattern",
            placeholder=pattern_placeholder,
            default=title_grouping_pattern,
            required=False,
            max_length=200,
            style=discord.TextStyle.short
        )
        
        # Field 5: Preferred Tags (comma-separated)
        self.preferred_tags_input = discord.ui.TextInput(
            label="Preferred Tags (comma-separated)",
            placeholder="e.g., Night Court, Day Court, Dawn Court",
            default=preferred_tags,
            required=False,
            max_length=500,
            style=discord.TextStyle.long
        )
        
        self.add_item(self.group_index_name_input)
        self.add_item(self.sort_by_tags_input)
        self.add_item(self.sort_by_title_pattern_input)
        self.add_item(self.title_grouping_pattern_input)
        self.add_item(self.preferred_tags_input)
        
        # Store other fields that aren't in the modal (we'll preserve them)
        self._priority_tag = priority_tag
        self._intro_text = intro_text
        self._thumb_url = config.get("thumb_url")
        self._use_character_sorting = config.get("use_character_sorting", False)
        self._thread_sort_by = thread_sort_by
        self._thread_sort_tag = thread_sort_tag
        self._source_forum_ids = config.get("source_forum_ids", [])
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Parse boolean fields
        sort_by_tags = self.config.get("sort_by_tags", False)  # Default to existing
        sort_by_tags_str = self.sort_by_tags_input.value.strip().lower()
        if sort_by_tags_str in ("true", "yes", "1", "on"):
            sort_by_tags = True
        elif sort_by_tags_str in ("false", "no", "0", "off"):
            sort_by_tags = False
        
        sort_by_title_pattern = self.config.get("sort_by_title_pattern", False)  # Default to existing
        sort_by_title_pattern_str = self.sort_by_title_pattern_input.value.strip().lower()
        if sort_by_title_pattern_str in ("true", "yes", "1", "on"):
            sort_by_title_pattern = True
        elif sort_by_title_pattern_str in ("false", "no", "0", "off"):
            sort_by_title_pattern = False
        
        # Get title grouping pattern
        title_grouping_pattern = self.title_grouping_pattern_input.value.strip() or None
        
        # Validate title pattern if provided
        if sort_by_title_pattern and not title_grouping_pattern:
            await interaction.followup.send(
                "❌ `title_grouping_pattern` is required when `sort_by_title_pattern` is true.",
                ephemeral=True
            )
            return
        
        # Parse preferred tags
        preferred_tags_str = self.preferred_tags_input.value.strip()
        preferred_tags_list = None
        if preferred_tags_str:
            preferred_tags_list = [tag.strip() for tag in preferred_tags_str.split(",") if tag.strip()]
        
        # Get other values
        group_index_name = self.group_index_name_input.value.strip()
        
        # Preserve existing values for fields not in modal
        intro_text = self._intro_text
        thumb_url = self._thumb_url
        use_character_sorting = self._use_character_sorting
        priority_tag = self._priority_tag or None
        thread_sort_by = self._thread_sort_by
        thread_sort_tag = self._thread_sort_tag
        source_forum_ids = self._source_forum_ids
        
        # Update group index configuration
        self.cog.config.add_group_index(
            guild_id=self.guild_id,
            target_channel_id=self.target_channel_id,
            group_index_name=group_index_name,
            source_forum_ids=source_forum_ids,
            sort_by_tags=sort_by_tags,
            preferred_tags=preferred_tags_list,
            intro_text=intro_text,
            thumb_url=thumb_url,
            priority_tag=priority_tag,
            sort_by_title_pattern=sort_by_title_pattern,
            title_grouping_pattern=title_grouping_pattern,
            thread_sort_by=thread_sort_by,
            thread_sort_tag=thread_sort_tag
        )
        
        # Refresh the group index
        await self.cog.refresh_group_index(self.guild_id, self.target_channel_id)
        
        # Build response message
        tag_info = ""
        if sort_by_tags:
            if preferred_tags_list:
                tag_info = f" (sorting by tags: {', '.join(preferred_tags_list)})"
            else:
                tag_info = " (sorting by all tags)"
        elif sort_by_title_pattern:
            tag_info = f" (sorting by title pattern: {title_grouping_pattern})"
        
        priority_info = ""
        if priority_tag:
            priority_info = f" (priority tag: {priority_tag})"
        
        guild = self.cog.bot.get_guild(self.guild_id)
        target_channel = guild.get_channel(self.target_channel_id) if guild else None
        channel_name = target_channel.name if target_channel else "Unknown"
        
        # Show forum management view after updating config
        edit_view = GroupIndexForumEditView(
            self.cog, self.guild_id, self.target_channel_id, 
            self._source_forum_ids, group_index_name
        )
        
        forum_count = len(self._source_forum_ids)
        response_msg = await interaction.followup.send(
            f"✅ Updated group index configuration for **{channel_name}** ({group_index_name}){tag_info}{priority_info}\n\n"
            f"**Forum Management:**\n"
            f"Currently using **{forum_count}** forum(s). Use the dropdowns below to add or remove forums, then click **Save and Finish**.",
            view=edit_view,
            ephemeral=True
        )
        edit_view.message = response_msg


class GroupIndexForumEditView(discord.ui.View):
    """View for managing source forums in a group index."""
    
    def __init__(self, cog: IndexManager, guild_id: int, target_channel_id: int, 
                 current_forum_ids: List[int], group_index_name: str):
        super().__init__(timeout=600)  # 10 minute timeout
        self.cog = cog
        self.guild_id = guild_id
        self.target_channel_id = target_channel_id
        self.current_forum_ids = current_forum_ids.copy()
        self.group_index_name = group_index_name
        self.message = None
        
        # Add forums select dropdown
        add_forum_select = discord.ui.ChannelSelect(
            placeholder="Select forums to ADD to this index...",
            channel_types=[discord.ChannelType.forum],
            max_values=25,
            min_values=1,
            row=0
        )
        add_forum_select.callback = self._on_add_forums_select
        self.add_item(add_forum_select)
        
        # Remove forums select dropdown
        remove_forum_select = discord.ui.ChannelSelect(
            placeholder="Select forums to REMOVE from this index...",
            channel_types=[discord.ChannelType.forum],
            max_values=25,
            min_values=1,
            row=1
        )
        remove_forum_select.callback = self._on_remove_forums_select
        self.add_item(remove_forum_select)
        
        # Save and finish button
        save_button = discord.ui.Button(label="Save and Finish", style=discord.ButtonStyle.success)
        save_button.callback = self._on_save
        self.add_item(save_button)
    
    async def _on_add_forums_select(self, interaction: discord.Interaction):
        """Handle adding forums."""
        if not interaction.data.get('values'):
            await interaction.response.send_message(
                "❌ No forums selected.",
                ephemeral=True
            )
            return
        
        guild = self.cog.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message(
                "❌ Guild not found.",
                ephemeral=True
            )
            return
        
        # Get channel IDs and fetch channels
        channel_ids = [int(ch_id) for ch_id in interaction.data['values']]
        added_forums = []
        
        for channel_id in channel_ids:
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.ForumChannel):
                if channel_id not in self.current_forum_ids:
                    self.current_forum_ids.append(channel_id)
                    added_forums.append(channel)
        
        if not added_forums:
            await interaction.response.send_message(
                "❌ All selected forums are already in the index.",
                ephemeral=True
            )
            return
        
        forum_names = [f.name for f in added_forums]
        await interaction.response.send_message(
            f"✅ Added **{len(added_forums)}** forum(s) to the index.\n"
            f"Forums added: {', '.join(forum_names[:5])}"
            + (f" and {len(added_forums) - 5} more..." if len(added_forums) > 5 else ""),
            ephemeral=True
        )
    
    async def _on_remove_forums_select(self, interaction: discord.Interaction):
        """Handle removing forums."""
        if not interaction.data.get('values'):
            await interaction.response.send_message(
                "❌ No forums selected.",
                ephemeral=True
            )
            return
        
        guild = self.cog.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message(
                "❌ Guild not found.",
                ephemeral=True
            )
            return
        
        # Get channel IDs and fetch channels
        channel_ids = [int(ch_id) for ch_id in interaction.data['values']]
        removed_forums = []
        
        for channel_id in channel_ids:
            if channel_id in self.current_forum_ids:
                self.current_forum_ids.remove(channel_id)
                channel = guild.get_channel(channel_id)
                if channel:
                    removed_forums.append(channel)
        
        if not removed_forums:
            await interaction.response.send_message(
                "❌ None of the selected forums are in the index.",
                ephemeral=True
            )
            return
        
        # Don't allow removing all forums
        if not self.current_forum_ids:
            # Re-add the forums back
            for ch_id in channel_ids:
                if ch_id not in self.current_forum_ids:
                    self.current_forum_ids.append(ch_id)
                # Also restore from removed_forums to get the order back
            for forum in removed_forums:
                if forum and forum.id not in self.current_forum_ids:
                    self.current_forum_ids.append(forum.id)
            await interaction.response.send_message(
                "❌ Cannot remove all forums. At least one forum must remain in the index.",
                ephemeral=True
            )
            return
        
        forum_names = [f.name for f in removed_forums if f]
        await interaction.response.send_message(
            f"✅ Removed **{len(removed_forums)}** forum(s) from the index.\n"
            f"Forums removed: {', '.join(forum_names[:5])}"
            + (f" and {len(removed_forums) - 5} more..." if len(removed_forums) > 5 else ""),
            ephemeral=True
        )
    
    async def _on_save(self, interaction: discord.Interaction):
        """Save the forum changes and finish."""
        if not self.current_forum_ids:
            await interaction.response.send_message(
                "❌ Cannot save: At least one forum must be in the index.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Get current config
        config = self.cog.config.get_group_index(self.guild_id, self.target_channel_id)
        if not config:
            await interaction.followup.send(
                "❌ Group index configuration not found.",
                ephemeral=True
            )
            return
        
        # Update config with new forum IDs
        self.cog.config.add_group_index(
            guild_id=self.guild_id,
            target_channel_id=self.target_channel_id,
            group_index_name=config.get("group_index_name", self.group_index_name),
            source_forum_ids=self.current_forum_ids,
            sort_by_tags=config.get("sort_by_tags", False),
            preferred_tags=config.get("preferred_tags"),
            intro_text=config.get("intro_text"),
            thumb_url=config.get("thumb_url"),
            use_character_sorting=config.get("use_character_sorting", False),
            priority_tag=config.get("priority_tag"),
            sort_by_title_pattern=config.get("sort_by_title_pattern", False),
            title_grouping_pattern=config.get("title_grouping_pattern"),
            thread_sort_by=config.get("thread_sort_by", "creation"),
            thread_sort_tag=config.get("thread_sort_tag")
        )
        
        # Refresh the group index
        guild = self.cog.bot.get_guild(self.guild_id)
        if guild:
            target_channel = guild.get_channel(self.target_channel_id)
            if target_channel:
                await self.cog.refresh_group_index(self.guild_id, self.target_channel_id)
        
        # Disable the view
        self.stop()
        for item in self.children:
            item.disabled = True
        
        # Update message if we have it
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        guild = self.cog.bot.get_guild(self.guild_id)
        target_channel = guild.get_channel(self.target_channel_id) if guild else None
        channel_name = target_channel.name if target_channel else "Unknown"
        
        await interaction.followup.send(
            f"✅ **Group Index Updated Successfully!**\n\n"
            f"**{channel_name}** ({self.group_index_name})\n"
            f"Now using **{len(self.current_forum_ids)}** forum(s).",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    cog = IndexManager(bot)
    # Set startup delay based on cog load order (index_manager loads first, so no delay)
    cog._startup_delay = 0
    await bot.add_cog(cog)
    # Remove existing command/group if it exists (for reloads)
    try:
        bot.tree.remove_command("index")
        print("[IndexManager] Removed existing index command")
    except Exception as e:
        print(f"[IndexManager] No existing index command to remove: {e}")
    # Add the index group
    try:
        bot.tree.add_command(cog.index_group)
        print("[IndexManager] Successfully added index group")
    except Exception as e:
        print(f"[IndexManager] ERROR: Failed to add index group: {e}")
        import traceback
        traceback.print_exc()

