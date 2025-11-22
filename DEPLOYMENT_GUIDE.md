# Deployment Guide: Discord Bot on SSH Server

This guide will walk you through deploying your Discord bot to a server accessible via SSH using Docker.

**Choose your deployment method:**
- **Method 1: Using Portainer (Web UI)** - Easier for beginners, visual interface
- **Method 2: Using Command Line** - Traditional Docker Compose method

## Prerequisites

Before you begin, make sure you have:
- A server with SSH access (Linux-based, like Ubuntu)
- Docker and Docker Compose installed on the server
- Your Discord bot token and other configuration values
- **For Portainer:** Portainer already set up and accessible via web browser
- **For Command Line:** Basic familiarity with terminal/command line

---

## Deployment Method 1: Using Portainer (Recommended for Beginners)

Portainer provides a web-based interface to manage Docker containers, making deployment much easier!

### Step 1: Transfer Your Bot Files to the Server

You need to get your bot files onto the server first. You have several options:

#### Option A: Using SFTP Client (Recommended - Easiest)

Use a GUI tool like **WinSCP** (Windows), **FileZilla**, or **Cyberduck** to drag and drop your files.

1. **Download WinSCP** (or your preferred SFTP client)
2. **Connect to your server:**
   - Protocol: `SFTP`
   - Host: `your-server-ip`
   - Port: `22`
   - Username: `your-ssh-username`
   - Password: `your-ssh-password`
3. **Navigate to your home directory** on the server (usually `/home/username/`)
4. **Create a folder** called `discord-bot` (right-click → New → Directory)
5. **Upload your files:**
   - On the left side (local), navigate to your bot folder
   - On the right side (server), navigate to `~/discord-bot`
   - Select all files and folders, then drag and drop to the server

**See the "Managing Files via SFTP" section below for detailed instructions.**

#### Option B: Using Git

If your code is in a Git repository:

```bash
# SSH into your server first
ssh username@your-server-ip

# Then clone the repository
cd ~
git clone https://github.com/your-username/your-repo.git discord-bot
cd discord-bot
```

#### Option C: Using SCP (Command Line)

From your **local machine** (not the server), run:

```bash
scp -r "C:\Users\Bambi\Desktop\Aether Utilties" username@your-server-ip:~/discord-bot
```

This will copy your entire project folder to the server's home directory as `discord-bot`.

### Step 2: Prepare Environment Variables

On your server, create the `.env` file. You have two options:

#### Option A: Using SFTP (Easier)

1. **Connect via SFTP** (see SFTP section below for setup)
2. **Navigate to** `~/discord-bot` on the server
3. **Download** `env.template` to your local machine
4. **Rename it** to `.env` on your local machine
5. **Edit it** with Notepad or your preferred editor
6. **Fill in your values:**
   - `DISCORD_TOKEN` - Your Discord bot token
   - `GUILD_ID` - Your Discord server ID
   - Add any other values you need
7. **Upload** the `.env` file back to `~/discord-bot/` on the server

#### Option B: Using SSH/Command Line

```bash
# SSH into your server
ssh username@your-server-ip

# Navigate to bot directory
cd ~/discord-bot

# Copy the template
cp env.template .env

# Edit the file
nano .env
```

**Minimum required values:**
- `DISCORD_TOKEN` - Your Discord bot token
- `GUILD_ID` - Your Discord server ID

Fill in all the values you need, then save the file (in nano: `Ctrl+X`, then `Y`, then `Enter`).

### Step 3: Access Portainer

1. Open your web browser and navigate to your Portainer URL (usually `http://your-server-ip:9000` or `https://your-server-ip:9443`)
2. Log in with your Portainer credentials

### Step 4: Create a New Stack

1. In Portainer, click on **"Stacks"** in the left sidebar
2. Click the **"+ Add stack"** button (or **"Create stack"**)
3. Give your stack a name: `discord-bot`

### Step 5: Upload docker-compose.yml

You have two options:

#### Option A: Web Editor (Easier)

1. In the stack creation page, you'll see a code editor
2. Open your `docker-compose.yml` file on your local machine
3. Copy the entire contents
4. Paste it into the Portainer web editor

#### Option B: Upload File

1. Click on **"Upload"** or **"Select file"** button
2. Navigate to and select your `docker-compose.yml` file

### Step 6: Configure Environment Variables

Since your `docker-compose.yml` uses `env_file: .env`, Portainer will automatically look for the `.env` file in the same directory as your `docker-compose.yml` file.

**Important:** Make sure your `.env` file is on the server in the same directory as `docker-compose.yml`:
```bash
# SSH into your server to verify
ssh username@your-server-ip
cd ~/discord-bot
ls -la  # You should see both docker-compose.yml and .env
```

**Alternative: Add variables directly in Portainer**
If you prefer not to use a `.env` file, you can add environment variables directly in Portainer:
1. In the stack editor, look for an **"Environment variables"** or **"Env"** section
2. Click **"Add environment variable"** for each variable:
   - `DISCORD_TOKEN` = `your_discord_bot_token_here`
   - `GUILD_ID` = `your_guild_id_here`
   - Add any other variables you need
3. If you use this method, you can remove or comment out the `env_file: .env` line in docker-compose.yml

**Recommended:** Use the `.env` file method as it's easier to manage and matches the command-line approach.

### Step 7: Configure Volumes and File Paths

Portainer needs to know where your files are located on the server:

1. In the stack editor, find the `volumes` section in docker-compose.yml
2. The paths should look like:
   ```yaml
   volumes:
     - ./data:/app/data
     - ./logs:/app/logs
   ```
3. **Important:** These paths (`./data`, `./logs`) are relative to where your `docker-compose.yml` file is located on the server
4. If your files are in `~/discord-bot`, these relative paths will work correctly

**Before deploying, make sure directories exist on your server:**
```bash
# SSH into server
ssh username@your-server-ip
cd ~/discord-bot
mkdir -p data logs
chmod 755 data logs
```

**Note:** When Portainer deploys a stack, it uses the directory where the `docker-compose.yml` file is located as the base path. So if your compose file is at `~/discord-bot/docker-compose.yml`, then `./data` refers to `~/discord-bot/data`.

### Step 8: Configure Build Arguments (Optional)

If your `requirements.txt` includes private GitHub repositories, you may need to set a build argument:

1. In the stack editor, look for **"Build arguments"** or **"Build"** section
2. Add a build argument:
   - Name: `GITHUB_TOKEN`
   - Value: `your_github_personal_access_token`
3. This is only needed if you have private repos in your requirements

**Note:** If you don't have private GitHub repositories, you can skip this step.

### Step 9: Deploy the Stack

1. Scroll to the bottom of the stack creation page
2. Click **"Deploy the stack"** button
3. Portainer will:
   - Build the Docker image (this may take a few minutes)
   - Create the container
   - Start the bot

**Watch the deployment:** You'll see a progress indicator. The first build can take 5-10 minutes depending on your server's speed.

### Step 10: Monitor Your Bot

1. After deployment, you'll be taken to the stack details page
2. Click on **"Containers"** in the left sidebar to see your running container
3. Click on the container name (`discord_bot`) to view details
4. Click on **"Logs"** tab to see the bot's output in real-time

### Managing Your Bot in Portainer

#### View Logs
- Go to **Containers** → Click on `discord_bot` → **Logs** tab
- You can follow logs in real-time or view historical logs

#### Restart the Bot
- Go to **Containers** → Click on `discord_bot` → Click **"Restart"** button

#### Stop the Bot
- Go to **Stacks** → Click on `discord-bot` → Click **"Stop"** button

#### Update the Bot (After Code Changes)

**Option 1: Using SFTP (Easiest)**
1. Edit files on your local machine
2. Upload changed files via SFTP to `~/discord-bot/`
3. In Portainer: Go to **Stacks** → `discord-bot` → **Editor** → **Update the stack**

**Option 2: Using Git**
1. **Update files on server:**
   ```bash
   # SSH into server
   ssh username@your-server-ip
   cd ~/discord-bot
   git pull
   ```

2. **In Portainer:**
   - Go to **Stacks** → Click on `discord-bot`
   - Click **"Editor"** tab
   - If you changed `docker-compose.yml`, update it here
   - Click **"Update the stack"**
   - Portainer will rebuild and restart the container

#### Rebuild After Code Changes
If you've updated the code and need to rebuild the image:

**Using SFTP:**
1. Upload your changed files via SFTP to `~/discord-bot/`
2. In Portainer: Go to **Stacks** → `discord-bot` → **Editor** → **Update the stack**

**Using Git:**
1. **Update files on server first:**
   ```bash
   ssh username@your-server-ip
   cd ~/discord-bot
   git pull  # or manually update files
   ```

2. **In Portainer:**
   - Go to **Stacks** → Click on `discord-bot`
   - Click **"Editor"** tab
   - Click **"Update the stack"** (this will trigger a rebuild)
   - Portainer will rebuild the image and restart the container

3. **Alternative method:**
   - Go to **Images** → Find your bot image
   - Click **"Build"** or **"Recreate"**
   - Then restart the container from **Containers** → `discord_bot` → **Restart**

### Troubleshooting in Portainer

#### Bot Won't Start
1. Check the **Logs** tab in the container view
2. Look for error messages (usually red text)
3. Common issues:
   - Missing `DISCORD_TOKEN` - Check environment variables
   - File permission errors - Check volume paths
   - Python errors - Check the logs for specific error messages

#### Container Keeps Restarting
1. Go to **Containers** → `discord_bot` → **Logs**
2. Look for error messages at the end of the logs
3. The logs will show why it's crashing

#### Can't See Logs
- Make sure the container is running (not stopped)
- Try refreshing the page
- Check if you have proper permissions in Portainer

#### Environment Variables Not Working
- If using `.env` file method, verify the file path is correct
- The `.env` file must be in the same directory as `docker-compose.yml`
- Or add variables directly in Portainer's environment section

---

## Managing Files via SFTP (Recommended for File Management)

SFTP (SSH File Transfer Protocol) allows you to manage your bot files using a graphical interface, making it much easier to edit files, upload changes, and manage your bot without using the command line.

### Recommended SFTP Clients for Windows

**Free Options:**
- **WinSCP** (Recommended) - https://winscp.net/ - Most popular, user-friendly
- **FileZilla** - https://filezilla-project.org/ - Cross-platform, well-known
- **Cyberduck** - https://cyberduck.io/ - Simple and clean interface

**Paid Options:**
- **MobaXterm** - Includes SFTP, SSH terminal, and more in one package
- **SecureFX** - Professional SFTP client

### Setting Up SFTP Connection

#### Using WinSCP (Recommended)

1. **Download and Install WinSCP**
   - Go to https://winscp.net/eng/download.php
   - Download the installer and run it

2. **Create a New Connection**
   - Open WinSCP
   - Click **"New Session"** or **"New Site"**
   - Fill in the connection details:
     - **File protocol:** `SFTP`
     - **Host name:** `your-server-ip` (or hostname)
     - **Port number:** `22` (default SSH port)
     - **User name:** `your-ssh-username`
     - **Password:** `your-ssh-password` (or use key file)
   
3. **Save the Connection**
   - Click **"Save"** to save this connection for future use
   - Give it a name like "Discord Bot Server"

4. **Connect**
   - Click **"Login"**
   - If this is your first time connecting, you'll see a security warning - click **"Yes"** to accept the server's fingerprint

#### Using FileZilla

1. **Download and Install FileZilla**
   - Go to https://filezilla-project.org/download.php?type=client
   - Download and install

2. **Create a New Site**
   - Click **"File"** → **"Site Manager"** (or press `Ctrl+S`)
   - Click **"New Site"**
   - Fill in:
     - **Protocol:** `SFTP - SSH File Transfer Protocol`
     - **Host:** `your-server-ip`
     - **Port:** `22`
     - **Logon Type:** `Normal`
     - **User:** `your-ssh-username`
     - **Password:** `your-ssh-password`

3. **Connect**
   - Click **"Connect"**

### Navigating to Your Bot Directory

Once connected, navigate to your bot directory:

1. In the **remote (server) side** of the SFTP client, navigate to:
   ```
   /home/your-username/discord-bot
   ```
   or
   ```
   ~/discord-bot
   ```

2. You should see your bot files:
   - `bot.py`
   - `docker-compose.yml`
   - `dockerfile`
   - `requirements.txt`
   - `cogs/` folder
   - `data/` folder
   - `core/` folder
   - `.env` file (if created)

### Common SFTP Tasks

#### Editing Files Directly on Server

**WinSCP:**
1. Right-click on any file (e.g., `bot.py`, `.env`)
2. Select **"Edit"**
3. WinSCP will download the file, open it in your default editor
4. Make your changes
5. Save the file
6. WinSCP will automatically upload it back to the server

**FileZilla:**
1. Right-click on a file
2. Select **"View/Edit"**
3. Choose your editor (Notepad++, VS Code, etc.)
4. Make changes and save
5. FileZilla will prompt to upload - click **"Yes"**

**Tip:** You can set your preferred editor in WinSCP: **Options** → **Preferences** → **Editors**

#### Uploading Files/Folders

**To upload a single file:**
- Drag and drop from your local computer to the server side
- Or right-click on local file → **"Upload"**

**To upload a folder:**
- Drag and drop the entire folder
- Or right-click → **"Upload"**

**To upload multiple files:**
- Select multiple files (hold `Ctrl` to select individual files, `Shift` for ranges)
- Drag and drop or right-click → **"Upload"**

#### Downloading Files/Folders

- Drag and drop from server side to local side
- Or right-click → **"Download"**

#### Creating New Files/Folders

**WinSCP:**
- Right-click in the file list → **"New"** → **"File"** or **"Directory"**

**FileZilla:**
- Right-click → **"Create directory"** or create file locally and upload

#### Editing the .env File

1. Navigate to your bot directory (`~/discord-bot`)
2. Right-click on `.env` → **"Edit"**
3. Make your changes (add/update environment variables)
4. Save the file
5. The file will be automatically uploaded back to the server

**Important:** After editing `.env`, you'll need to restart your bot in Portainer for changes to take effect.

### Workflow: Making Code Changes

Here's a typical workflow when you want to update your bot code:

1. **Edit files locally** (on your Windows machine)
   - Use your favorite code editor (VS Code, Notepad++, etc.)
   - Make your changes to Python files, configs, etc.

2. **Upload changed files via SFTP**
   - Connect via SFTP
   - Navigate to `~/discord-bot`
   - Upload the changed files (drag and drop or right-click → Upload)
   - Or upload entire folders if you changed multiple files

3. **Restart/Rebuild in Portainer**
   - Go to Portainer → **Stacks** → `discord-bot`
   - Click **"Editor"** tab
   - Click **"Update the stack"** (this rebuilds and restarts)
   - Or go to **Containers** → `discord_bot` → **Restart**

### Managing Data Files

Your bot stores data in the `data/` folder. You can manage these files via SFTP:

**Viewing data files:**
- Navigate to `~/discord-bot/data/`
- You'll see JSON files like:
  - `mia_state.json`
  - `lore_carousels.json`
  - `proxies.json`

**Backing up data:**
- Select the `data/` folder
- Right-click → **"Download"**
- Save it to a safe location on your local machine

**Restoring data:**
- Upload your backup `data/` folder to `~/discord-bot/data/`
- Make sure to preserve file permissions

**Editing data files:**
- Right-click on any JSON file → **"Edit"**
- Make changes and save
- The file will be uploaded automatically

### Viewing Logs via SFTP

If you've set up log persistence, you can view log files:

1. Navigate to `~/discord-bot/logs/` (if the folder exists)
2. Download log files to view them locally
3. Or edit them directly if they're text files

**Note:** For real-time logs, it's better to use Portainer's log viewer.

### File Permissions

Sometimes you may need to set file permissions:

**In WinSCP:**
1. Right-click on file/folder → **"Properties"**
2. Set permissions (e.g., `755` for directories, `644` for files)
3. Click **"OK"**

**Common permissions:**
- Directories: `755` (rwxr-xr-x)
- Files: `644` (rw-r--r--)
- Executable scripts: `755`

### Tips and Best Practices

1. **Always backup before major changes**
   - Download your `data/` folder before making significant updates
   - Keep backups of your `.env` file

2. **Use SFTP for file management, Portainer for container management**
   - SFTP: Edit code, manage data files, upload/download
   - Portainer: Start/stop containers, view logs, manage Docker

3. **Keep your local and server files in sync**
   - Consider using Git for version control
   - Or keep a local copy of your bot files

4. **Be careful with the `.env` file**
   - Never share it or commit it to Git
   - Always edit it carefully - typos can break your bot

5. **Test changes incrementally**
   - Make small changes, upload, test
   - Don't upload everything at once if you're unsure

### Troubleshooting SFTP

**Can't connect:**
- Verify your server IP address
- Check that SSH is enabled on port 22
- Verify your username and password
- Check your firewall settings

**Permission denied errors:**
- Make sure you're using the correct user account
- Check file permissions (right-click → Properties)
- Some files may require `sudo` - you can't edit these via SFTP

**Files not updating:**
- Make sure you saved the file after editing
- Check that the upload completed successfully
- Restart the container in Portainer to pick up changes

**Connection drops:**
- SFTP connections may timeout after inactivity
- Simply reconnect when needed
- Some clients have "keep-alive" options to prevent timeouts

---

## Deployment Method 2: Using Command Line (Traditional Method)

If you prefer using the command line or don't have Portainer set up:

---

## Step 1: Install Docker and Docker Compose on Your Server

### Connect to Your Server

Open your terminal (PowerShell on Windows, Terminal on Mac/Linux) and connect via SSH:

```bash
ssh username@your-server-ip
```

Replace:
- `username` with your SSH username
- `your-server-ip` with your server's IP address or hostname

### Install Docker

**For Ubuntu/Debian:**

```bash
# Update package index
sudo apt-get update

# Install required packages
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to docker group (so you don't need sudo for docker commands)
sudo usermod -aG docker $USER

# Log out and back in for group changes to take effect
exit
```

**Reconnect to your server:**
```bash
ssh username@your-server-ip
```

**Verify Docker installation:**
```bash
docker --version
docker compose version
```

---

## Step 2 (CLI Method): Transfer Your Bot Files to the Server

You have several options to transfer files:

### Option A: Using SCP (from your local machine)

From your **local machine** (not the server), run:

```bash
scp -r "C:\Users\Bambi\Desktop\Aether Utilties" username@your-server-ip:~/discord-bot
```

This will copy your entire project folder to the server's home directory as `discord-bot`.

### Option B: Using Git (Recommended)

If your code is in a Git repository:

```bash
# On your server
cd ~
git clone https://github.com/your-username/your-repo.git discord-bot
cd discord-bot
```

### Option C: Using SFTP Client

Use a GUI tool like WinSCP (Windows), FileZilla, or Cyberduck to drag and drop your files.

---

## Step 3 (CLI Method): Set Up Environment Variables

### Create the .env File

On your server, navigate to the bot directory:

```bash
cd ~/discord-bot
# or wherever you placed the files
```

Create a `.env` file. You can copy from the template:

```bash
cp env.template .env
nano .env
```

Or create it manually:

```bash
nano .env
```

Fill in your actual values. Here's what you need at minimum:

```bash
# Required: Your Discord Bot Token
DISCORD_TOKEN=your_discord_bot_token_here

# Required: Your Discord Server (Guild) ID
GUILD_ID=your_guild_id_here
```

**See `env.template` for all available configuration options.** Most settings are optional and have sensible defaults.

**To save in nano:** Press `Ctrl+X`, then `Y`, then `Enter`.

**Important:** Never share your `.env` file or commit it to Git!

---

## Step 4 (CLI Method): Build and Start the Bot

### Build the Docker Image

```bash
cd ~/discord-bot
docker compose build
```

If you have private GitHub repositories in your requirements.txt, you can optionally pass a GitHub token:

```bash
GITHUB_TOKEN=your_github_token docker compose build
```

### Start the Bot

```bash
docker compose up -d
```

The `-d` flag runs it in "detached" mode (in the background).

### Check if It's Running

```bash
docker compose ps
```

You should see your container running. You can also check the logs:

```bash
docker compose logs -f
```

Press `Ctrl+C` to exit the log viewer (this won't stop the bot).

---

## Step 5 (CLI Method): Managing Your Bot

### View Logs

```bash
# View recent logs
docker compose logs

# Follow logs in real-time
docker compose logs -f

# View last 100 lines
docker compose logs --tail=100
```

### Stop the Bot

```bash
docker compose down
```

### Restart the Bot

```bash
docker compose restart
```

### Update the Bot (After Code Changes)

```bash
# Pull latest code (if using Git)
git pull

# Rebuild the image
docker compose build

# Restart the container
docker compose up -d
```

### Check Bot Status

```bash
# See if container is running
docker compose ps

# Check resource usage
docker stats discord_bot
```

---

## Step 6 (CLI Method): Set Up Automatic Restart on Server Reboot

The `restart: unless-stopped` setting in `docker-compose.yml` should handle this, but to ensure Docker starts on boot:

```bash
sudo systemctl enable docker
sudo systemctl enable containerd
```

---

## Troubleshooting

### Bot Won't Start

1. **Check logs:**
   ```bash
   docker compose logs
   ```

2. **Verify .env file exists and has correct values:**
   ```bash
   cat .env
   ```

3. **Check if port conflicts exist (usually not an issue for Discord bots):**
   ```bash
   docker compose ps
   ```

### Container Keeps Restarting

This usually means the bot is crashing. Check logs:

```bash
docker compose logs --tail=50
```

Common issues:
- Missing or incorrect `DISCORD_TOKEN` in `.env`
- Missing required environment variables
- Python errors in the code

### Permission Errors

If you get permission errors:

```bash
# Make sure your user is in the docker group
sudo usermod -aG docker $USER
# Then log out and back in
```

### Can't Connect to Server via SSH

- Verify your server's IP address
- Check if SSH is enabled on the server
- Ensure your firewall allows SSH (port 22)
- Verify your SSH credentials

### Data Files Not Persisting

Make sure the `data` directory exists and has proper permissions:

```bash
mkdir -p ~/discord-bot/data
chmod 755 ~/discord-bot/data
```

---

## Security Best Practices

1. **Never commit `.env` to Git** - It contains sensitive tokens
2. **Use strong passwords** for your SSH account
3. **Keep Docker updated:**
   ```bash
   sudo apt-get update && sudo apt-get upgrade docker-ce
   ```
4. **Regular backups** - Backup your `data` directory:
   ```bash
   tar -czf bot-backup-$(date +%Y%m%d).tar.gz ~/discord-bot/data
   ```

---

## Quick Reference

### SFTP Quick Reference

- **Connect:** Use WinSCP/FileZilla with your server credentials
- **Edit Files:** Right-click → Edit (auto-uploads after save)
- **Upload Files:** Drag and drop or right-click → Upload
- **Download Files:** Drag and drop or right-click → Download
- **Bot Directory:** `~/discord-bot` or `/home/username/discord-bot`

### Portainer Quick Reference

- **View Logs:** Stacks → `discord-bot` → Containers → `discord_bot` → Logs tab
- **Restart:** Stacks → `discord-bot` → Stop/Start buttons, or Containers → `discord_bot` → Restart
- **Update Stack:** Stacks → `discord-bot` → Editor tab → Update the stack
- **Check Status:** Stacks → `discord-bot` → Overview tab, or Containers → `discord_bot`

### Command Line Quick Reference

```bash
# Navigate to bot directory
cd ~/discord-bot

# Start bot
docker compose up -d

# Stop bot
docker compose down

# View logs
docker compose logs -f

# Restart bot
docker compose restart

# Rebuild after code changes
docker compose build && docker compose up -d

# Check status
docker compose ps
```

---

## Next Steps

- Set up log rotation if logs get too large
- Configure monitoring/alerting if the bot goes down
- Set up automated backups of your data directory
- Consider using a process manager like `systemd` for additional control

---

## Getting Help

If you encounter issues:
1. Check the logs first: `docker compose logs`
2. Verify your `.env` file has all required variables
3. Ensure Docker is running: `docker ps`
4. Check if the container is healthy: `docker compose ps`

Good luck with your deployment! 🚀

