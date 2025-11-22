# Archivist-Utilities
A comprehensive Discord bot designed for roleplay servers, featuring character management, quest systems, dice challenges, lore carousels, and automated indexing capabilities.

## Features

### 🎭 Character Management
- **Character Search**: Fuzzy search across multiple character forums
- **Character Forums**: Configurable forum channels for character organization
- **Character Movement**: Move characters between forums (NPC, graveyard, active characters)

### 📚 Index Management
- **Automatic Indexing**: Auto-generate and maintain index threads for forums
- **Tag-based Sorting**: Organize entries by tags or alphabetically
- **Auto-refresh**: Indexes update automatically every 6 hours
- **Customizable**: Configure index names, thumbnails, and intro text

### 🎲 Dice Challenges
- **Challenge Tracking**: Track wins, losses, and streaks for characters
- **Interactive Buttons**: Easy-to-use interface for recording challenges
- **Admin Approval**: Optional approval workflow for challenge results
- **Statistics**: View detailed challenge history and statistics

### 📖 Lore Carousel
- **Interactive Pages**: Create paginated information displays
- **Navigation Controls**: Easy navigation between pages with dropdown and buttons
- **Admin Management**: Add, edit, and remove pages via admin menu
- **Image Support**: Add images via URL or file attachments

### 🎯 Quest System
- **Random Quest Hooks**: Generate random quest hooks with Accept/Skip options
- **Quest Reservations**: Reserve quests for 30 days
- **Skip Protection**: Prevents duplicate quests in recent history

### 🧵 Thread Management
- **Thread Movement**: Move threads between forums or channels
- **Message Preservation**: Copies all messages and attachments
- **Archive Options**: Automatically archive original threads

### 🤖 Additional Features
- **Post as Bot**: Administrators can post messages as the bot
- **Reaction-based Actions**: Various features triggered by emoji reactions
- **Hot Reloading**: Automatic code reloading during development (cogwatch)
- **AI Integration**: OpenAI integration for advanced features (optional)

## Prerequisites

- Python 3.10 or higher
- Discord Bot Token ([Get one here](https://discord.com/developers/applications))
- Docker and Docker Compose (optional)


### Required Environment Variables

Create a `.env` file (copy from `env.template`):

```env
# Required
DISCORD_TOKEN=your_discord_bot_token_here
```

### Getting Your Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application or select an existing one
3. Go to the "Bot" section
4. Click "Reset Token" or "Copy" to get your token
5. Enable the following Privileged Gateway Intents:
   - Message Content Intent
   - Server Members Intent

## Usage

### Commands

The bot uses Discord slash commands. Type `/` in Discord to see available commands.

**Key Commands:**
- `/character search` - Find a character by name
- `/quest start` - Get a random quest hook
- `/challenge view` - View character challenge statistics
- `/lore create` - Create a new lore carousel
- `/index add` - Add a forum to automatic indexing
- `/move thread` - Move a thread to another location

### Setting Up Features

#### Character Search
1. Use `/character add` to add forum channels containing character threads
2. The bot will automatically cache character names
3. Users can search with `/character search`

#### Automatic Indexing
1. Use `/index add` to configure a forum for automatic indexing
2. The bot creates an index thread that updates every 6 hours
3. Use `/index refresh` to manually update

#### Dice Challenges
1. Use `/challenge set_channel` to configure challenge channels
2. Set up the button channel where users can finish challenges
3. Optionally enable admin approval workflow

#### Lore Carousel
1. Use `/lore create` in a channel to create a carousel
2. Add pages with `/lore add` or use the admin menu
3. Users can navigate with Previous/Next buttons or dropdown

## Project Structure

```
Aether Utilties/
├── bot.py                 # Main bot entry point
├── cogs/                  # Bot command modules
│   ├── characters.py      # Character search and management
│   ├── quests.py          # Quest system
│   ├── dice_challenges.py # Dice challenge tracking
│   ├── lore_carousel.py   # Interactive lore carousels
│   ├── index_manager.py   # Automatic forum indexing
│   ├── move.py            # Thread movement commands
│   └── ...                # Other feature modules
├── core/                  # Core utilities
│   ├── config.py          # Configuration management
│   ├── utils.py           # Utility functions
│   └── http.py            # HTTP client utilities
├── data/                  # Data storage (JSON files)
├── logs/                  # Log files
├── docker-compose.yml     # Docker Compose configuration
├── dockerfile             # Docker image definition
├── requirements.txt       # Python dependencies
├── env.template           # Environment variable template
└── README.md              # This file
```

## Development

### Hot Reloading

The bot supports automatic code reloading during development:

1. Set `ENABLE_COGWATCH=true` in your `.env` file
2. Edit any file in the `cogs/` directory
3. The bot will automatically reload the changed cog

For Docker environments, set `USE_POLLING_WATCHER=true` for more reliable file watching.

### Adding New Features

1. Create a new file in the `cogs/` directory
2. Follow the existing cog structure (inherit from `commands.Cog`)
3. Add the cog to the `COGS` list in `bot.py`
4. The bot will automatically load it on restart

### Code Style

- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Document functions and classes with docstrings
- Use Discord.py's slash command system (`@app_commands.command`)

## Deployment

### Docker Deployment

The bot is designed to run in Docker containers. See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for:
- Portainer deployment (web UI)
- Command-line deployment
- SFTP file management
- Troubleshooting
## Dependencies

Key dependencies:
- `discord.py` - Discord API wrapper
- `httpx` - HTTP client
- `aiohttp` - Async HTTP client
- `openai` - OpenAI API client (for AI features)
- `rapidfuzz` - Fuzzy string matching
- `cogwatch` - Hot reloading for development
- `python-dotenv` - Environment variable management

See [requirements.txt](requirements.txt) for the complete list.

## Troubleshooting

### Bot Won't Start
- Check that `DISCORD_TOKEN` is set in `.env`
- Verify the bot token is valid and not expired
- Check logs: `docker compose logs` or `python bot.py`

### Commands Not Appearing
- Commands may take a few minutes to sync after bot restart
- Use `/` in Discord to check if commands are available
- Restart the bot to force command sync

### Character Search Not Working
- Ensure character forums are configured with `/character add`
- The cache refreshes every 24 hours automatically
- Use `/character list` to verify configured forums

### Index Not Updating
- Use `/index refresh` to manually trigger an update
- Check that the forum is configured with `/index list`
- Indexes update automatically every 6 hours

## Security Notes

- **Never commit `.env` to Git** - It contains sensitive tokens
- Keep your Discord bot token secure
- Use environment variables for all sensitive configuration
- Regularly update dependencies for security patches


## Support

MultiMuse Support Discord: https://discord.gg/nd6FUaBpaV

**Note:** This bot is designed for roleplay Discord servers. Some features may require specific server setups (forums, channels, etc.) to function properly.

