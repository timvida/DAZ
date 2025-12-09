-- Database migration for Player Events and Webhooks
-- Add this to your SQLite database

-- Player Events Table
CREATE TABLE IF NOT EXISTS player_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp DATETIME NOT NULL,
    position_x FLOAT,
    position_y FLOAT,
    position_z FLOAT,
    killer_id INTEGER,
    killer_name VARCHAR(120),
    weapon VARCHAR(120),
    distance FLOAT,
    cause_of_death VARCHAR(120),
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES game_servers(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (killer_id) REFERENCES players(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_player_events_server ON player_events(server_id);
CREATE INDEX IF NOT EXISTS idx_player_events_player ON player_events(player_id);
CREATE INDEX IF NOT EXISTS idx_player_events_type ON player_events(event_type);
CREATE INDEX IF NOT EXISTS idx_player_events_timestamp ON player_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_player_event_type ON player_events(player_id, event_type);
CREATE INDEX IF NOT EXISTS idx_server_event_timestamp ON player_events(server_id, timestamp);

-- Webhook Config Table
CREATE TABLE IF NOT EXISTS webhook_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL UNIQUE,
    unconscious_webhook_url VARCHAR(512),
    death_webhook_url VARCHAR(512),
    suicide_webhook_url VARCHAR(512),
    unconscious_enabled BOOLEAN DEFAULT 0,
    death_enabled BOOLEAN DEFAULT 0,
    suicide_enabled BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES game_servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_webhook_configs_server ON webhook_configs(server_id);

-- Player Stats Table
CREATE TABLE IF NOT EXISTS player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL UNIQUE,
    total_kills INTEGER DEFAULT 0,
    total_deaths INTEGER DEFAULT 0,
    suicide_count INTEGER DEFAULT 0,
    unconscious_count INTEGER DEFAULT 0,
    longest_kill_distance FLOAT DEFAULT 0.0,
    longest_kill_weapon VARCHAR(120),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats(player_id);
