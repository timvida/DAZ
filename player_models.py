from database import db
from datetime import datetime
import secrets
import string

class Player(db.Model):
    """Main player model - one entry per unique player (by GUID)"""
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('game_servers.id'), nullable=False)

    # Unique Identifiers
    dayztools_id = db.Column(db.String(16), unique=True, nullable=False, index=True)  # Custom 16-char ID
    guid = db.Column(db.String(64), nullable=False, index=True)  # BattlEye GUID (primary identifier)
    steam_id = db.Column(db.String(20), index=True)  # Steam ID 64
    bohemia_id = db.Column(db.String(128))  # Bohemia Interactive ID

    # Current Data (latest known values)
    current_name = db.Column(db.String(120))
    current_ip = db.Column(db.String(45))  # IPv6 compatible
    current_port = db.Column(db.Integer)

    # Status
    is_online = db.Column(db.Boolean, default=False)

    # Statistics
    total_playtime = db.Column(db.Integer, default=0)  # Total playtime in seconds
    session_count = db.Column(db.Integer, default=0)  # Number of sessions
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)  # First time on server
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)  # Last time on server

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = db.relationship('PlayerSession', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    name_history = db.relationship('PlayerName', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    ip_history = db.relationship('PlayerIP', backref='player', lazy='dynamic', cascade='all, delete-orphan')

    # Unique constraint on server_id + guid (one player per server)
    __table_args__ = (
        db.UniqueConstraint('server_id', 'guid', name='unique_server_player'),
        db.Index('idx_player_lookup', 'server_id', 'guid'),
        db.Index('idx_player_steam', 'steam_id'),
    )

    @staticmethod
    def generate_dayztools_id():
        """Generate unique 16-character DayZTools ID"""
        chars = string.ascii_uppercase + string.digits
        while True:
            dayztools_id = ''.join(secrets.choice(chars) for _ in range(16))
            # Check if ID already exists
            if not Player.query.filter_by(dayztools_id=dayztools_id).first():
                return dayztools_id

    def __repr__(self):
        return f'<Player {self.current_name} ({self.guid})>'


class PlayerSession(db.Model):
    """Individual player sessions - join/leave events"""
    __tablename__ = 'player_sessions'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)

    # Session data
    join_time = db.Column(db.DateTime, nullable=False, index=True)
    leave_time = db.Column(db.DateTime)  # NULL if still online
    duration = db.Column(db.Integer)  # Duration in seconds (calculated when leaving)

    # Session snapshot data (what was known at join time)
    name_at_join = db.Column(db.String(120))
    ip_at_join = db.Column(db.String(45))
    port_at_join = db.Column(db.Integer)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_session_player_time', 'player_id', 'join_time'),
    )

    def __repr__(self):
        return f'<PlayerSession {self.player_id} @ {self.join_time}>'


class PlayerName(db.Model):
    """Player name history - tracks name changes"""
    __tablename__ = 'player_names'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)

    name = db.Column(db.String(120), nullable=False)
    first_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usage_count = db.Column(db.Integer, default=1)  # How many times this name was used

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_name_player', 'player_id', 'name'),
    )

    def __repr__(self):
        return f'<PlayerName {self.name}>'


class PlayerIP(db.Model):
    """Player IP history - tracks IP changes"""
    __tablename__ = 'player_ips'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False, index=True)

    ip_address = db.Column(db.String(45), nullable=False)
    port = db.Column(db.Integer)
    first_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usage_count = db.Column(db.Integer, default=1)  # How many times this IP was used

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_ip_player', 'player_id', 'ip_address'),
    )

    def __repr__(self):
        return f'<PlayerIP {self.ip_address}>'
