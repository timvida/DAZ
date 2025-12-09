"""
Player Event Models - Track deaths, kills, unconscious states, etc.
"""
from database import db
from datetime import datetime


class PlayerEvent(db.Model):
    """
    Player events from ADM logs
    Tracks deaths, kills, unconscious states, suicides
    """
    __tablename__ = 'player_events'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('game_servers.id', ondelete='CASCADE'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id', ondelete='CASCADE'), nullable=False, index=True)

    # Event details
    event_type = db.Column(db.String(50), nullable=False, index=True)  # 'death', 'kill', 'unconscious', 'regained_consciousness', 'suicide'
    timestamp = db.Column(db.DateTime, nullable=False, index=True)

    # Location
    position_x = db.Column(db.Float)
    position_y = db.Column(db.Float)
    position_z = db.Column(db.Float)

    # Death/Kill specific
    killer_id = db.Column(db.Integer, db.ForeignKey('players.id', ondelete='SET NULL'), nullable=True)  # NULL if killed by infected/environment
    killer_name = db.Column(db.String(120))  # Name at time of kill
    weapon = db.Column(db.String(120))  # Weapon used
    distance = db.Column(db.Float)  # Distance in meters (for ranged kills)

    # Death cause (if not killed by player)
    cause_of_death = db.Column(db.String(120))  # 'Infected', 'Bled out', 'Environment', 'Suicide', etc.

    # Additional details (JSON string for extensibility)
    details = db.Column(db.Text)  # JSON: {"hp": 100, "water": 500, "energy": 600, "bleed_sources": 2}

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        db.Index('idx_player_event_type', 'player_id', 'event_type'),
        db.Index('idx_server_event_timestamp', 'server_id', 'timestamp'),
    )

    def __repr__(self):
        return f'<PlayerEvent {self.id} - {self.event_type}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'server_id': self.server_id,
            'player_id': self.player_id,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'position': {
                'x': self.position_x,
                'y': self.position_y,
                'z': self.position_z
            } if self.position_x else None,
            'killer_id': self.killer_id,
            'killer_name': self.killer_name,
            'weapon': self.weapon,
            'distance': self.distance,
            'cause_of_death': self.cause_of_death,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class WebhookConfig(db.Model):
    """
    Discord Webhook configurations per server
    """
    __tablename__ = 'webhook_configs'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('game_servers.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Webhook URLs
    unconscious_webhook_url = db.Column(db.String(512))
    death_webhook_url = db.Column(db.String(512))
    suicide_webhook_url = db.Column(db.String(512))

    # Enable/Disable toggles
    unconscious_enabled = db.Column(db.Boolean, default=False)
    death_enabled = db.Column(db.Boolean, default=False)
    suicide_enabled = db.Column(db.Boolean, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<WebhookConfig server_id={self.server_id}>'

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'server_id': self.server_id,
            'unconscious_webhook_url': self.unconscious_webhook_url,
            'death_webhook_url': self.death_webhook_url,
            'suicide_webhook_url': self.suicide_webhook_url,
            'unconscious_enabled': self.unconscious_enabled,
            'death_enabled': self.death_enabled,
            'suicide_enabled': self.suicide_enabled,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class PlayerStats(db.Model):
    """
    Player statistics (kills, deaths, K/D ratio)
    """
    __tablename__ = 'player_stats'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Combat stats
    total_kills = db.Column(db.Integer, default=0)
    total_deaths = db.Column(db.Integer, default=0)
    suicide_count = db.Column(db.Integer, default=0)
    unconscious_count = db.Column(db.Integer, default=0)

    # Longest kill
    longest_kill_distance = db.Column(db.Float, default=0.0)
    longest_kill_weapon = db.Column(db.String(120))

    # Timestamps
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<PlayerStats player_id={self.player_id} K:{self.total_kills} D:{self.total_deaths}>'

    @property
    def kd_ratio(self):
        """Calculate K/D ratio"""
        if self.total_deaths == 0:
            return self.total_kills if self.total_kills > 0 else 0.0
        return round(self.total_kills / self.total_deaths, 2)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'player_id': self.player_id,
            'total_kills': self.total_kills,
            'total_deaths': self.total_deaths,
            'suicide_count': self.suicide_count,
            'unconscious_count': self.unconscious_count,
            'kd_ratio': self.kd_ratio,
            'longest_kill_distance': self.longest_kill_distance,
            'longest_kill_weapon': self.longest_kill_weapon,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
