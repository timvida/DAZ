from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    """Admin user model"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if password matches"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class SteamAccount(db.Model):
    """Steam account credentials"""
    __tablename__ = 'steam_accounts'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    last_verified = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SteamAccount {self.username}>'


class GameServer(db.Model):
    """Game server instances"""
    __tablename__ = 'game_servers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    game_name = db.Column(db.String(80), nullable=False)  # e.g., "DayZ"
    app_id = db.Column(db.Integer, nullable=False)  # Steam App ID
    install_path = db.Column(db.String(255), nullable=False)

    # DayZ-specific configuration
    server_port = db.Column(db.Integer, default=2302)
    rcon_port = db.Column(db.Integer, default=2306)
    rcon_password = db.Column(db.String(255))
    cpu_count = db.Column(db.Integer)
    profile_path = db.Column(db.String(255))
    be_path = db.Column(db.String(255))
    mods = db.Column(db.Text, default='')  # Semicolon-separated mod paths
    server_mods = db.Column(db.Text, default='')  # Semicolon-separated server mod paths

    # Server status and management
    port = db.Column(db.Integer)  # Legacy field, kept for compatibility
    status = db.Column(db.String(20), default='stopped')  # stopped, running, installing, updating
    is_installed = db.Column(db.Boolean, default=False)
    process_id = db.Column(db.Integer)  # PID of running server process
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Auto-update system for DayZ server
    update_available = db.Column(db.Boolean, default=False)  # Is a server update available?
    update_downloaded = db.Column(db.Boolean, default=False)  # Has the update been downloaded?
    last_update_check = db.Column(db.DateTime)  # Last time we checked for updates

    # Relationship to mods
    server_mods_rel = db.relationship('ServerMod', backref='server', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<GameServer {self.name} ({self.game_name})>'


class ServerMod(db.Model):
    """Server mod instances"""
    __tablename__ = 'server_mods'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('game_servers.id'), nullable=False)

    # Mod identification
    mod_name = db.Column(db.String(120), nullable=False)  # Display name
    mod_folder = db.Column(db.String(120), nullable=False)  # @ModName
    workshop_id = db.Column(db.String(50))  # Steam Workshop ID (optional)

    # Mod configuration
    mod_type = db.Column(db.String(20), default='client')  # client, server, or both
    is_active = db.Column(db.Boolean, default=False)  # Is mod enabled?
    auto_update = db.Column(db.Boolean, default=False)  # Auto-update via Steam?

    # Mod management
    keys_copied = db.Column(db.Boolean, default=False)  # Keys copied to server/keys?
    file_size = db.Column(db.BigInteger)  # Size in bytes
    last_updated = db.Column(db.DateTime)  # Last update timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ServerMod {self.mod_name} ({self.mod_folder})>'


class ServerScheduler(db.Model):
    """Server scheduler for automated tasks"""
    __tablename__ = 'server_schedulers'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('game_servers.id'), nullable=False)

    # Schedule configuration
    name = db.Column(db.String(120), nullable=False)  # User-friendly name
    schedule_type = db.Column(db.String(20), default='cron')  # "cron" (fixed time) or "interval" (every X minutes)
    hour = db.Column(db.Integer, nullable=True)  # Hour (0-23) - only for cron
    minute = db.Column(db.Integer, nullable=True)  # Minute (0-59) - only for cron
    weekdays = db.Column(db.String(50), nullable=True)  # Comma-separated: "0,1,2,3,4,5,6" - only for cron
    interval_minutes = db.Column(db.Integer, nullable=True)  # Interval in minutes - only for interval

    # Action configuration
    action_type = db.Column(db.String(50), nullable=False)  # "restart" or "message"

    # Restart action settings
    kick_all_players = db.Column(db.Boolean, default=True)  # Kick all players before restart
    kick_minutes_before = db.Column(db.Integer, default=1)  # Minutes before restart to kick
    warning_minutes = db.Column(db.Text)  # JSON array of warning times: "[60,30,15,10,5,3,2,1]"

    # Message action settings
    custom_message = db.Column(db.Text)  # Custom message to send

    # Scheduler status
    is_active = db.Column(db.Boolean, default=True)  # Is scheduler enabled?
    last_run = db.Column(db.DateTime)  # Last execution time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    server = db.relationship('GameServer', backref=db.backref('schedulers', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ServerScheduler {self.name} ({self.action_type})>'
