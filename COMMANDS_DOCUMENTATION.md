# Aether Utilities Bot - Commands Documentation

This document provides a comprehensive overview of all available commands in the Archivist Discord bot.

---

## Table of Contents

1. [Character Management](#character-management)
2. [Index Management](#index-management)
3. [Thread Management](#thread-management)
4. [Quest System](#quest-system)
5. [Dice Challenges](#dice-challenges)
6. [Lore Carousel](#lore-carousel)
7. [Reaction-Based Features](#reaction-based-features)

---

## Character Management

### `/character search`
**Description:** Find a character by name using fuzzy matching  
**Usage:** `/character search name:<character_name>`  
**Parameters:**
- `name` (required): Character name to search for (supports autocomplete and partial matches)

**Permissions:** Everyone  
**Details:** Searches through configured character forums to find a character thread. Uses substring matching first, then falls back to fuzzy matching if no exact match is found. Returns a link to the character thread.

### `/character add`
**Description:** Add a forum channel to the character search system  
**Usage:** `/character add forum:<forum_channel>`  
**Parameters:**
- `forum` (required): The forum channel containing character threads

**Permissions:** Administrator only  
**Details:** Adds a forum channel to the list of forums that the character search command will search through. Immediately rebuilds the cache for that forum.

### `/character remove`
**Description:** Remove a forum channel from character search  
**Usage:** `/character remove forum:<forum_channel>`  
**Parameters:**
- `forum` (required): The forum channel to remove from character search

**Permissions:** Administrator only  
**Details:** Removes a forum channel from the character search system and rebuilds the cache.

### `/character list`
**Description:** List all configured character forums  
**Usage:** `/character list`  
**Permissions:** Administrator only  
**Details:** Shows all forum channels currently configured for character search in the current guild.

---

## Index Management

All index commands require **Administrator** permissions.

### `/index add`
**Description:** Add a forum to the automatic index system  
**Usage:** `/index add forum:<forum> index_name:<name> [sort_by_tags:<true/false>] [preferred_tags:<tags>] [index_thread_name:<name>] [intro_text:<text>] [thumb_url:<url>]`  
**Parameters:**
- `forum` (required): The forum channel to index
- `index_name` (required): Name for this index (e.g., "Characters", "Resources")
- `sort_by_tags` (optional): Whether to group entries by tags (default: false)
- `preferred_tags` (optional): Comma-separated list of preferred tags to sort by (only used if sort_by_tags is true)
- `index_thread_name` (optional): Name for the index thread (defaults to "📜 {index_name} Index")
- `intro_text` (optional): Intro text for the index thread
- `thumb_url` (optional): Thumbnail URL for the index thread

**Details:** Creates an automatic index thread that lists all threads in a forum. The index updates automatically every 6 hours and can be sorted by tags or alphabetically. Supports special character sorting for character forums.

### `/index refresh`
**Description:** Refresh one or all indexes  
**Usage:** `/index refresh [forum:<forum>]`  
**Parameters:**
- `forum` (optional): Specific forum to refresh (leave empty to refresh all)

**Details:** Manually triggers an index refresh. If no forum is specified, refreshes all indexes in the guild.

### `/index list`
**Description:** List all configured indexes  
**Usage:** `/index list`  
**Details:** Shows all forums currently configured for automatic indexing in the current guild.

### `/index remove`
**Description:** Remove an index configuration  
**Usage:** `/index remove forum:<forum>`  
**Parameters:**
- `forum` (required): The forum channel to remove from indexing

**Details:** Removes a forum from the automatic index system. The index thread will not be deleted, but it will stop updating automatically.

### `/index migrate`
**Description:** Migrate old hardcoded indexes from settings (one-time migration)  
**Usage:** `/index migrate`  
**Details:** One-time command to migrate old hardcoded index configurations from settings to the new flexible index system. Migrates Character Backstories, Encyclopedia, and Resources indexes if they exist in settings.

---

## Thread Management

### `/move thread`
**Description:** Move the current thread to any target forum or text channel  
**Usage:** `/move thread destination:<channel> [rename:<new_name>] [archive_original:<true/false>]`  
**Parameters:**
- `destination` (required): The destination forum or text channel
- `rename` (optional): Optionally rename the thread when moving
- `archive_original` (optional): Archive and lock the original thread after moving (default: true)

**Permissions:** Everyone (must be used inside a thread)  
**Details:** Copies all messages and attachments from the current thread to a new location. If moving to a forum, creates a new thread. If moving to a text channel, posts messages directly. By default, archives and locks the original thread.

### `/move character`
**Description:** Move the current thread to another character forum (NPC, graveyard, or characters)  
**Usage:** `/move character destination:<npc|graveyard|characters> [played_by:<name>] [cause_of_death:<text>]`  
**Parameters:**
- `destination` (required): One of: `npc`, `graveyard`, or `characters`
- `played_by` (optional): Who played this character (required for graveyard)
- `cause_of_death` (optional): Cause of death (required for graveyard)

**Permissions:** Everyone (must be used inside a thread)  
**Details:** Specialized move command for character threads. When moving to graveyard, adds metadata about who played the character and cause of death. Copies all messages and attachments to the new location.

---

## Quest System

### `/quest start`
**Description:** Roll a random quest hook with Accept/Skip options  
**Usage:** `/quest start`  
**Permissions:** Everyone  
**Details:** Generates a random quest hook and displays it as an embed with Accept and Skip buttons. You can skip up to 3 times per session. If you already have an active quest reservation, it will show that instead.

**Features:**
- Accept: Reserves the quest for 30 days
- Skip: Get a new random quest (max 3 skips per session)
- Tracks recent quests to avoid showing duplicates

### `/quest current`
**Description:** Show your current quest reservation (if any)  
**Usage:** `/quest current`  
**Permissions:** Everyone  
**Details:** Displays your currently active quest reservation, including when it expires. Shows a message if you don't have an active reservation.

### `/quest release`
**Description:** Release your current quest reservation  
**Usage:** `/quest release [title:<quest_title>]`  
**Parameters:**
- `title` (optional): Specific quest title to release (if omitted, releases your current reservation)

**Permissions:** Everyone  
**Details:** Releases your active quest reservation, making it available for others. If you don't specify a title, it releases your current reservation automatically.

---

## Dice Challenges

### `/challenge view`
**Description:** View a character's dice challenge record  
**Usage:** `/challenge view character:<character_name>`  
**Parameters:**
- `character` (required): Character name to view (supports fuzzy matching)

**Permissions:** Everyone  
**Details:** Shows a character's complete challenge record including:
- Total wins and losses
- Current win streak
- Current loss streak
- Total games played
- Last 10 games history

### `/challenge adjust`
**Description:** Manually adjust a character's challenge record  
**Usage:** `/challenge adjust character:<character_name>`  
**Parameters:**
- `character` (required): Character name to adjust (supports fuzzy matching)

**Permissions:** Administrator only  
**Details:** Opens a modal to manually adjust a character's challenge statistics:
- Total Wins
- Total Losses
- Current Win Streak
- Current Loss Streak
- Total Games

### `/challenge reset`
**Description:** Reset a character's challenge record to zero  
**Usage:** `/challenge reset character:<character_name>`  
**Parameters:**
- `character` (required): Character name to reset (supports fuzzy matching)

**Permissions:** Administrator only  
**Details:** Completely resets a character's challenge record, clearing all wins, losses, streaks, and game history.

### `/challenge set_channel`
**Description:** Configure challenge channels for this server  
**Usage:** `/challenge set_channel [button_channel:<channel>] [approval_channel:<channel>] [approvals_enabled:<true/false>]`  
**Parameters:**
- `button_channel` (optional): Channel where the finish challenge button will appear
- `approval_channel` (optional): Channel where challenge results are sent for approval
- `approvals_enabled` (optional): Whether to require admin approval before posting results (default: true)

**Permissions:** Administrator only  
**Details:** Configures the dice challenge system for your server. Sets up channels for the finish challenge button and approval workflow. If approvals are disabled, results are posted immediately without admin review.

### `/challenge configure_message`
**Description:** Configure the format of challenge result messages  
**Usage:** `/challenge configure_message`  
**Permissions:** Administrator only  
**Details:** Opens an interactive interface to customize how challenge results are displayed in character threads. You can:
- Edit the message header
- Toggle which fields to display (current streak, total wins, total losses, total games, streak warnings)

### Finish Challenge Button
**Description:** Interactive button to record a completed dice challenge  
**Usage:** Click the "🎲 Finish Dice Challenge" button in the configured button channel  
**Permissions:** Everyone  
**Details:** Opens a modal to enter two challenger names. After entering names, you select the winner. The result is then sent for admin approval (if enabled) or posted immediately to both character threads.

**Features:**
- Automatically finds character threads using fuzzy matching
- Updates win/loss streaks
- Posts results to character threads
- Tracks game history (last 10 games)
- Shows streak warnings for 3+ consecutive losses

---

## Lore Carousel

The Lore Carousel system allows you to create interactive, paginated information displays in channels. Perfect for displaying lore, character creation guides, magic systems, or any other information that benefits from organized pages.

### `/lore create`
**Description:** Create a new lore carousel in the current channel  
**Usage:** `/lore create initial_header:<header> initial_body:<body> [image_url:<url>] [attachment:<file>]`  
**Parameters:**
- `initial_header` (required): Header/title for the first page (max 256 characters)
- `initial_body` (required): Body content for the first page (max 2000 characters)
- `image_url` (optional): Image URL for the first page (HTTP/HTTPS)
- `attachment` (optional): Image attachment for the first page (alternative to image_url)

**Permissions:** Administrator only  
**Details:** Creates a new interactive carousel in the current channel with an initial page. The carousel will display with navigation controls and an admin menu. You can add more pages after creation.

### `/lore add`
**Description:** Add a new page to an existing carousel in this channel  
**Usage:** `/lore add header:<header> body:<body> [image_url:<url>] [attachment:<file>]`  
**Parameters:**
- `header` (required): Header/title for the new page (max 256 characters)
- `body` (required): Body content for the new page (max 2000 characters)
- `image_url` (optional): Image URL for the new page (HTTP/HTTPS)
- `attachment` (optional): Image attachment for the new page (alternative to image_url)

**Permissions:** Administrator only  
**Details:** Adds a new page to an existing carousel. The page will immediately appear in the carousel's dropdown menu and can be navigated to using the Previous/Next buttons.

### `/lore remove`
**Description:** Remove a lore carousel from this channel  
**Usage:** `/lore remove`  
**Permissions:** Administrator only  
**Details:** Completely removes the carousel from the current channel, including all pages and the carousel message. This action cannot be undone.

### Interactive Carousel Features

Once a carousel is created, it displays with the following interactive elements:

**Navigation Controls:**
- **Dropdown Menu:** Select any page directly from the dropdown menu
- **◀ Previous Button:** Navigate to the previous page (wraps to last page)
- **Next ▶ Button:** Navigate to the next page (wraps to first page)

**Admin Menu (⚙️ Admin Menu Button):**
- **➕ Add Page:** Opens a modal to add a new page with header, body, and optional image URL
- **✏️ Edit Page:** Opens a modal to edit an existing page (selects page if multiple exist)
- **🗑️ Remove Page:** Removes a page from the carousel (with confirmation, cannot remove last page)

**Features:**
- All pages are stored persistently and survive bot restarts
- Images can be added via URL or file attachment
- Body content supports up to 2000 characters per page
- Admin actions are only functional for users with administrator permissions
- Page counter shows current position (e.g., "Page 1 of 5")

**Notes:**
- Each channel can have one carousel
- You cannot remove the last page (must delete the carousel instead)
- Admin menu button is visible to everyone but only functional for administrators
- Carousel messages are automatically restored on bot restart

---

## Reaction-Based Features

### Post as Bot (✏️ Emoji)
**Description:** Post a message as the bot by starting with ✏️ emoji  
**Usage:** Type `✏️ <your message>`  
**Permissions:** Administrator only  
**Details:** Allows administrators to post messages as the bot. Start your message with the ✏️ emoji followed by your content. The bot will post the message and delete your original message.

**Requirements:**
- Administrator permissions
- Message must start with ✏️ emoji
- Can include text and/or attachments

---

## Notes

- All slash commands use Discord's autocomplete where applicable
- Commands that require administrator permissions will show an error if you don't have the required permissions
- Some commands are ephemeral (only visible to you) while others post publicly
- The bot automatically handles rate limiting and retries for API calls
- Index updates happen automatically every 6 hours

---

## Troubleshooting

**Commands not appearing:**
- Commands may take a few minutes to appear after bot restart
- Restart the bot to reload commands if needed

**Character search not working:**
- Ensure character forums are configured with `/character add`
- The cache refreshes every 24 hours automatically

**Index not updating:**
- Use `/index refresh` to manually trigger an update
- Check that the forum is properly configured with `/index list`

**Quest system not responding:**
- Ensure `QUEST_GSCRIPT_URL` and `QUEST_GSCRIPT_SECRET` environment variables are set
- Check bot logs for webhook errors

---

*Last updated: Based on current codebase analysis*

