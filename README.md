# GameServer Web Interface

A modern, self-hosted web interface for managing game servers. Built with Python Flask and designed with simplicity in mind.

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## Features

- **Easy Installation**: One-command installation script that sets up everything automatically
- **Modern Dark UI**: Clean, intuitive interface with a modern dark theme
- **Steam Integration**: Direct integration with SteamCMD for downloading and updating game servers
- **Multi-Game Support**: Pre-configured for DayZ, Rust, ARK, and custom games
- **Server Management**: Install, start, stop, update, and delete game servers
- **Secure**: Password hashing, session management, and secure credential storage
- **Self-Hosted**: All data stays on your own server

## Supported Games

- **DayZ** (App ID: 223350)
- **Rust** (App ID: 258550)
- **ARK: Survival Evolved** (App ID: 376030)
- **Custom games** (any SteamCMD-compatible game)

## Requirements

- Linux server (Ubuntu, Debian, CentOS, RHEL)
- Python 3.8 or higher
- SteamCMD
- Steam account (without 2FA recommended for automatic updates)

## Quick Installation

1. **Clone or download this repository**:
   ```bash
   git clone https://github.com/yourusername/gameserver-webinterface.git
   cd gameserver-webinterface
   ```

2. **Make the install script executable**:
   ```bash
   chmod +x install.sh
   ```

3. **Run the installation**:
   ```bash
   ./install.sh
   ```

The install script will:
- Detect your operating system
- Install Python3 and pip (if not already installed)
- Install SteamCMD (if not already installed)
- Create a Python virtual environment
- Install all required dependencies
- Start the web server

4. **Access the installation wizard**:
   Open your browser and navigate to:
   ```
   http://YOUR_SERVER_IP:29911/install
   ```

## Installation Wizard

### Step 1: Admin Account
Create your administrator account:
- Username
- Email address
- Password (minimum 6 characters)

### Step 2: Steam Account
Configure Steam credentials for downloading game servers:
- Steam username
- Steam password

**Important**: Use a Steam account **without 2FA/Steam Guard** enabled to simplify automatic updates. Your credentials are stored securely on your own server and are never shared.

### Step 3: Complete
Finalize the installation and start managing your servers!

## Usage

### Creating a Server

1. Log in to the dashboard
2. Use the "Create New Server" form
3. Select a game or enter a custom Steam App ID
4. Click "Create Server"

### Installing a Server

1. Click the "Install Server" button on a server card
2. Wait for the installation to complete (this may take several minutes)
3. The server will be marked as installed when complete

### Starting/Stopping Servers

- Click "Start" to start a stopped server
- Click "Stop" to stop a running server

### Updating Servers

- Click "Update" on an installed server to download the latest version

### Deleting Servers

- Click "Delete" to remove a server and all its files
- Confirm the deletion (this action cannot be undone)

## Configuration

### Changing the Port

Edit `config.py` and change the `PORT` value:
```python
PORT = 29911  # Change to your desired port
```

### Custom SteamCMD Path

If SteamCMD is installed in a non-standard location, edit `config.py`:
```python
STEAMCMD_PATH = '/path/to/steamcmd.sh'
```

### Server Files Location

By default, game servers are installed in the `servers/` directory. To change this, edit `config.py`:
```python
SERVERS_DIR = '/custom/path/to/servers'
```

## Firewall Configuration

Make sure port 29911 (or your custom port) is open:

**Ubuntu/Debian (ufw)**:
```bash
sudo ufw allow 29911/tcp
```

**CentOS/RHEL (firewalld)**:
```bash
sudo firewall-cmd --permanent --add-port=29911/tcp
sudo firewall-cmd --reload
```

## Manual Startup

If you need to start the server manually:

```bash
cd gameserver-webinterface
source venv/bin/activate
python3 app.py
```

## Running as a Service

To run the web interface as a systemd service, create `/etc/systemd/system/gameserver-web.service`:

```ini
[Unit]
Description=GameServer Web Interface
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/gameserver-webinterface
ExecStart=/path/to/gameserver-webinterface/venv/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gameserver-web
sudo systemctl start gameserver-web
```

## Security Recommendations

1. **Use HTTPS**: Set up a reverse proxy (nginx/Apache) with SSL certificates
2. **Strong Passwords**: Use strong, unique passwords for the admin account
3. **Firewall**: Only allow necessary ports
4. **Regular Updates**: Keep the system and dependencies updated
5. **Dedicated Steam Account**: Use a separate Steam account for server management

## Troubleshooting

### Installation Issues

**Python not found**:
```bash
sudo apt-get install python3 python3-pip python3-venv
```

**SteamCMD not found**:
```bash
sudo dpkg --add-architecture i386
sudo apt-get update
sudo apt-get install lib32gcc-s1 steamcmd
```

### Server Won't Start

Check if the port is already in use:
```bash
sudo netstat -tulpn | grep 29911
```

### Steam Verification Fails

- Make sure the Steam account credentials are correct
- Verify that 2FA/Steam Guard is disabled
- Check your internet connection
- Try again later if Steam rate limits are encountered

## Project Structure

```
gameserver-webinterface/
├── install.sh              # Installation script
├── requirements.txt        # Python dependencies
├── app.py                  # Main Flask application
├── config.py               # Configuration file
├── database.py             # Database models
├── steam_utils.py          # Steam/SteamCMD utilities
├── server_manager.py       # Server management logic
├── static/
│   ├── css/
│   │   └── style.css       # Modern dark theme styles
│   └── js/
│       └── main.js         # Frontend JavaScript
├── templates/
│   ├── base.html           # Base template
│   ├── install.html        # Installation wizard
│   ├── login.html          # Login page
│   └── dashboard.html      # Main dashboard
├── servers/                # Game server files (created automatically)
├── venv/                   # Python virtual environment (created automatically)
└── gameserver.db           # SQLite database (created automatically)
```

## Technologies Used

- **Backend**: Python 3, Flask, SQLAlchemy
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Database**: SQLite
- **Game Server Management**: SteamCMD
- **Security**: Werkzeug password hashing, Flask sessions

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

This project is open source and available under the MIT License.

## Support

If you encounter any issues or have questions:
1. Check the Troubleshooting section
2. Review existing issues on GitHub
3. Open a new issue with detailed information

## Roadmap

Future planned features:
- [ ] Multi-user support with different permission levels
- [ ] Server console output streaming
- [ ] Automated backup system
- [ ] Server monitoring and statistics
- [ ] Email notifications
- [ ] Docker support
- [ ] API endpoints for automation

## Credits

Created with ❤️ for the gaming community.

---

**Happy Gaming!** 🎮
