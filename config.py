import os
import secrets

class Config:
    """Application configuration"""

    # Base directory
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # Secret key for sessions
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

    # Database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'gameserver.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Server settings
    HOST = '0.0.0.0'
    PORT = 29911
    DEBUG = False

    # SteamCMD paths
    STEAMCMD_PATH = os.path.expanduser('~/steamcmd/steamcmd.sh')
    STEAMCMD_ALT_PATH = '/usr/games/steamcmd'

    # Game servers directory
    SERVERS_DIR = os.path.join(BASE_DIR, 'servers')

    # Installation lock file
    INSTALL_LOCK = os.path.join(BASE_DIR, '.installed')

    # Session timeout (30 minutes)
    PERMANENT_SESSION_LIFETIME = 1800
