"""
DayZ BattlEye RCon Utility
Using the proven 'rcon' package (https://github.com/conqp/rcon)
"""

import logging
from threading import Lock

logger = logging.getLogger(__name__)

try:
    from rcon.battleye import Client
    RCON_AVAILABLE = True
except ImportError:
    logger.error("rcon package not available - install with: pip install rcon")
    RCON_AVAILABLE = False


class BattlEyeRCon:
    """BattlEye RCon client for DayZ servers using proven rcon package"""

    def __init__(self, host, port, password):
        """
        Initialize RCon connection

        Args:
            host: Server IP address
            port: RCon port
            password: RCon password
        """
        self.host = host
        self.port = int(port)
        self.password = password
        self.authenticated = False
        self.lock = Lock()

    def connect(self, timeout=5):
        """
        Connect to the BattlEye RCon server

        Args:
            timeout: Connection timeout in seconds

        Returns:
            tuple: (success: bool, message: str)
        """
        if not RCON_AVAILABLE:
            return False, "rcon package not installed"

        try:
            logger.info(f"Connecting to BattlEye RCon at {self.host}:{self.port}")

            # Test connection by sending a simple command using context manager
            try:
                with Client(self.host, self.port, passwd=self.password, timeout=timeout) as client:
                    response = client.run('players')
                    self.authenticated = True
                    logger.info(f"Successfully connected to RCon")
                    return True, "Connected successfully"
            except Exception as e:
                error_msg = str(e)
                if 'password' in error_msg.lower() or 'login' in error_msg.lower():
                    logger.warning("Login failed - invalid password")
                    return False, "Invalid password"
                logger.error(f"Connection test failed: {error_msg}")
                return False, f"Connection failed: {error_msg}"

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False, f"Connection error: {str(e)}"

    def send_command(self, command, timeout=5):
        """
        Send a command to the server

        Args:
            command: Command string to execute
            timeout: Command timeout in seconds

        Returns:
            tuple: (success: bool, response: str)
        """
        if not self.authenticated:
            return False, "Not authenticated"

        with self.lock:
            try:
                logger.debug(f"Sending command: {command}")

                # Parse command into parts
                parts = command.split()
                if not parts:
                    return False, "Empty command"

                # Send command using context manager
                with Client(self.host, self.port, passwd=self.password, timeout=timeout) as client:
                    response = client.run(*parts)

                    # Convert response to string if needed
                    if response is None:
                        response = ""
                    elif not isinstance(response, str):
                        response = str(response)

                    logger.debug(f"Command response: {response[:100] if response else '(empty)'}")
                    return True, response

            except Exception as e:
                logger.error(f"Command error: {str(e)}")
                return False, f"Command error: {str(e)}"

    def send_message(self, message):
        """
        Send a global message to all players

        Args:
            message: Message to send

        Returns:
            tuple: (success: bool, response: str)
        """
        command = f'say -1 {message}'
        return self.send_command(command)

    def get_players(self):
        """
        Get list of online players

        Returns:
            tuple: (success: bool, players: list)
        """
        success, response = self.send_command('players')

        if not success:
            return False, []

        # Parse player list
        players = []
        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip()
                if not line or 'Players on server' in line or line.startswith('---'):
                    continue

                # Parse player line
                # Format: ID IP:Port Ping GUID(BE) Name
                parts = line.split(None, 4)
                if len(parts) >= 2:
                    try:
                        player = {
                            'id': parts[0],
                            'ip': parts[1] if len(parts) > 1 else 'Unknown',
                            'ping': parts[2] if len(parts) > 2 else 'N/A',
                            'guid': parts[3] if len(parts) > 3 else 'N/A',
                            'name': parts[4] if len(parts) > 4 else 'Unknown'
                        }
                        players.append(player)
                    except:
                        continue

            return True, players
        except Exception as e:
            logger.error(f"Error parsing players: {str(e)}")
            return False, []

    def kick_all_players(self):
        """
        Kick all players from the server

        Returns:
            tuple: (success: bool, message: str)
        """
        success, players = self.get_players()

        if not success:
            return False, "Failed to get player list"

        kicked = 0
        for player in players:
            self.send_command(f'kick {player["id"]}')
            kicked += 1

        return True, f"Kicked {kicked} player(s)"

    def kick_player(self, player_id):
        """
        Kick a specific player

        Args:
            player_id: Player ID to kick

        Returns:
            tuple: (success: bool, response: str)
        """
        return self.send_command(f'kick {player_id}')

    def disconnect(self):
        """Close the RCon connection"""
        # Client is managed by context managers, just reset auth state
        self.authenticated = False

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()


class RConManager:
    """Manager for RCon operations on game servers"""

    @staticmethod
    def read_battleye_config(server):
        """
        Read BattlEye configuration from the actual config file

        Args:
            server: GameServer instance

        Returns:
            dict: Config values (rcon_password, rcon_port, rcon_ip) or None
        """
        import os
        import glob

        try:
            be_path = server.be_path
            if not os.path.exists(be_path):
                logger.warning(f"BattlEye path does not exist: {be_path}")
                return None

            # Find beserver_x64*.cfg file (with or without hash)
            pattern = os.path.join(be_path, 'beserver_x64*.cfg')
            config_files = glob.glob(pattern)

            pattern_lower = os.path.join(be_path, 'BEServer_x64*.cfg')
            config_files.extend(glob.glob(pattern_lower))

            # Filter out .so files
            config_files = [f for f in config_files if not f.endswith('.so')]

            if not config_files:
                logger.warning(f"No BattlEye config file found in {be_path}")
                return None

            config_file = config_files[0]
            logger.info(f"Reading BattlEye config from: {config_file}")

            config = {}
            config['_config_file'] = os.path.basename(config_file)

            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    if line.startswith('RConPassword'):
                        parts = line.split(None, 1)
                        if len(parts) > 1:
                            password = parts[1].strip()
                            # Remove inline comments
                            if '#' in password:
                                password = password.split('#')[0].strip()
                            config['rcon_password'] = password
                            config['_password_length'] = len(password)
                            logger.info(f"Found RConPassword: length={len(password)}")

                    elif line.startswith('RConPort'):
                        parts = line.split(None, 1)
                        if len(parts) > 1:
                            try:
                                port_str = parts[1].strip()
                                if '#' in port_str:
                                    port_str = port_str.split('#')[0].strip()
                                config['rcon_port'] = int(port_str)
                                logger.info(f"Found RConPort: {config['rcon_port']}")
                            except Exception as e:
                                logger.error(f"Error parsing port: {e}")

                    elif line.startswith('RConIP'):
                        parts = line.split(None, 1)
                        if len(parts) > 1:
                            ip = parts[1].strip()
                            if '#' in ip:
                                ip = ip.split('#')[0].strip()
                            config['rcon_ip'] = ip
                            logger.info(f"Found RConIP: {ip}")

            logger.info(f"BattlEye config read: Port={config.get('rcon_port')}, IP={config.get('rcon_ip')}, PwLen={config.get('_password_length')}")
            return config if config else None

        except Exception as e:
            logger.error(f"Error reading BattlEye config: {str(e)}")
            return None

    @staticmethod
    def get_rcon_connection(server):
        """Get an RCon connection for a server"""
        be_config = RConManager.read_battleye_config(server)

        if be_config:
            rcon_password = be_config.get('rcon_password', server.rcon_password)
            rcon_port = be_config.get('rcon_port', server.rcon_port)
            rcon_ip = be_config.get('rcon_ip', None)
            logger.info(f"Using BattlEye config: Port={rcon_port}, IP={rcon_ip}")
        else:
            logger.warning("Could not read BattlEye config, using database values")
            rcon_password = server.rcon_password
            rcon_port = server.rcon_port
            rcon_ip = None

        # Convert 0.0.0.0 to actual server IP or localhost
        if not rcon_ip or rcon_ip == '0.0.0.0':
            from server_manager import ServerManager
            server_manager = ServerManager()
            rcon_ip = server_manager._get_server_ip()

            if not rcon_ip or rcon_ip == '0.0.0.0':
                rcon_ip = '127.0.0.1'

        logger.info(f"Connecting to RCon at {rcon_ip}:{rcon_port}")
        return BattlEyeRCon(rcon_ip, rcon_port, rcon_password)

    @staticmethod
    def test_connection(server):
        """Test RCon connection"""
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()

                if success:
                    cmd_success, response = rcon.send_command('players')
                    details = {
                        'connected': True,
                        'authenticated': True,
                        'response_time': 'OK',
                        'server_ip': rcon.host,
                        'rcon_port': rcon.port
                    }
                    return True, "RCon connection successful", details
                else:
                    details = {
                        'connected': False,
                        'authenticated': False,
                        'error': msg,
                        'server_ip': rcon.host,
                        'rcon_port': rcon.port
                    }
                    return False, f"Connection failed: {msg}", details

        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            details = {'connected': False, 'error': str(e)}
            return False, f"Error: {str(e)}", details

    @staticmethod
    def get_players(server):
        """Get list of online players"""
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, [], f"Failed to connect: {msg}"

                success, players = rcon.get_players()
                if success:
                    return True, players, f"Found {len(players)} player(s)"
                else:
                    return False, [], "Failed to get players"

        except Exception as e:
            logger.error(f"Error getting players: {str(e)}")
            return False, [], f"Error: {str(e)}"

    @staticmethod
    def send_server_message(server, message):
        """Send a message to all players"""
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                success, response = rcon.send_message(message)
                if success:
                    return True, f"Message sent: {message}"
                else:
                    return False, f"Failed to send message: {response}"

        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def kick_all_players(server):
        """Kick all players"""
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.kick_all_players()

        except Exception as e:
            logger.error(f"Error kicking players: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def execute_command(server, command):
        """Execute a custom RCon command"""
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.send_command(command)

        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return False, f"Error: {str(e)}"
