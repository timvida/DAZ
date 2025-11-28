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
