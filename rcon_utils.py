"""
DayZ BattlEye RCon Utility - Enhanced Version
Robust implementation with auto-reconnect, async receiving and keep-alive
Based on proven BattlEye protocol implementation with decorator pattern
"""

import socket
import struct
import binascii
import time
import threading
import functools
import logging
import glob
import os

logger = logging.getLogger(__name__)


# --- DECORATOR: CONNECTION GUARD ---
def ensure_connection(func):
    """
    Decorator that ensures RCon connection is active before executing commands.
    Automatically attempts to reconnect if connection is lost.

    Args:
        func: Function to wrap

    Returns:
        Wrapped function with connection check
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.authenticated or not self.running:
            # Attempt reconnection
            logger.warning(f"Connection lost. Attempting reconnect for '{func.__name__}'...")
            success, msg = self.connect()
            if not success:
                logger.error(f"ABORT: Command '{func.__name__}' could not be sent (server offline).")
                return False, f"Connection failed: {msg}"

        try:
            # Execute the actual function
            return func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error executing '{func.__name__}': {e}")
            self.disconnect()  # Close socket on error to force reconnect next time
            return False, f"Error: {str(e)}"
    return wrapper


class BattlEyeRCon:
    """Enhanced BattlEye RCon client for DayZ servers with auto-reconnect"""

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
        self.sock = None
        self.sequence = 0
        self.authenticated = False
        self.running = False

        # Threads and synchronization
        self.listener_thread = None
        self.last_response = ""
        self.response_lock = threading.Lock()
        self.response_buffer = []

    def connect(self, timeout=10):
        """
        Connect to the BattlEye RCon server

        Args:
            timeout: Connection timeout in seconds

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Clean up any existing connection
            self.disconnect(silent=True)

            logger.info(f"Connecting to BattlEye RCon at {self.host}:{self.port}")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(timeout)

            # Send login packet
            payload = b'\x00' + self.password.encode('utf-8')
            packet = self._create_packet(payload)
            self.sock.sendto(packet, (self.host, self.port))

            # Wait for login confirmation
            data, _ = self.sock.recvfrom(4096)

            if len(data) >= 8:
                # Check login response
                # Response format: BE + CRC32 + 0xFF + 0x00 + (0x01 success | 0x00 failed)
                if data[6] == 0xFF and data[7] == 0x00:
                    if len(data) > 8 and data[8] == 0x01:
                        self.authenticated = True
                        self.running = True
                        logger.info("✅ Login successful! Connection established.")

                        # Start background thread (Keep-Alive + Listener)
                        self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
                        self.listener_thread.start()
                        return True, "Connected successfully"
                    else:
                        logger.warning("Login failed - invalid password")
                        return False, "Invalid password"

            return False, "Unexpected login response"

        except socket.timeout:
            logger.error("Login timeout. Server unreachable or wrong port.")
            return False, "Connection timeout"
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False, f"Connection error: {str(e)}"

    def disconnect(self, silent=False):
        """
        Close the RCon connection

        Args:
            silent: If True, don't log the disconnection
        """
        self.running = False
        self.authenticated = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        if not silent:
            logger.info("Connection closed.")

    def _create_packet(self, payload):
        """
        Create BattlEye packet with header and CRC32

        Args:
            payload: Packet payload (without 0xFF header)

        Returns:
            bytes: Complete packet
        """
        # BattlEye Packet Structure: 'BE' + CRC32 + 0xFF + Payload
        head = b'\xFF'
        data_to_checksum = head + payload

        # Calculate CRC32 checksum (unsigned int)
        crc = binascii.crc32(data_to_checksum) & 0xffffffff

        # Pack: BE, CRC (Little Endian), Payload (with 0xFF header)
        return b'BE' + struct.pack('<I', crc) + data_to_checksum

    def _listener_loop(self):
        """
        Background process:
        1. Receives data from server
        2. Sends keep-alive packets
        """
        last_keep_alive = time.time()

        while self.running:
            try:
                # A. Keep Alive (Every 30 seconds)
                if time.time() - last_keep_alive > 30:
                    # Send empty command packet to keep connection alive
                    ka_payload = b'\x01' + struct.pack('B', self.sequence) + b''
                    self.sock.sendto(self._create_packet(ka_payload), (self.host, self.port))
                    last_keep_alive = time.time()
                    logger.debug("Keep-alive packet sent")

                # B. Receive data (non-blocking check via socket timeout)
                try:
                    self.sock.settimeout(0.5)  # Short timeout for responsive keep-alive
                    data, _ = self.sock.recvfrom(4096)
                except socket.timeout:
                    continue  # Just continue looping
                except OSError:
                    break  # Socket closed

                if len(data) < 7:
                    continue  # Too short for header

                # Parse header (first 2 'BE', then 4 CRC, then 1 flag)
                flag = data[6]
                payload = data[7:]

                if flag == 0x02:  # Command Response
                    # Remove sequence byte (first byte of payload with flag 0x02)
                    text_response = payload[1:].decode('utf-8', errors='ignore')

                    # Store for retrieving function
                    with self.response_lock:
                        self.last_response += text_response
                        self.response_buffer.append(text_response)

                elif flag == 0x00:  # Login Response (shouldn't happen in loop)
                    pass

            except Exception as e:
                logger.error(f"Error in listener thread: {e}")
                break

    def send_command(self, command, timeout=2.0):
        """
        Send a command to the server

        Args:
            command: Command string to execute
            timeout: Time to wait for response in seconds

        Returns:
            tuple: (success: bool, response: str)
        """
        if not self.authenticated:
            return False, "Not authenticated"

        with self.response_lock:
            try:
                self.sequence = (self.sequence + 1) % 256
                payload = b'\x01' + struct.pack('B', self.sequence) + command.encode('utf-8')
                packet = self._create_packet(payload)

                # Clear buffer before new command
                self.last_response = ""
                self.response_buffer.clear()

                # Send packet
                self.sock.sendto(packet, (self.host, self.port))
                logger.debug(f"Sending command: {command}")

            except Exception as e:
                logger.error(f"Send error: {e}")
                return False, f"Send error: {str(e)}"

        # Wait for response (UDP has no clear "end of message", so time-based)
        time.sleep(timeout)

        with self.response_lock:
            response = self.last_response.strip()
            logger.debug(f"Command response: {response[:100] if response else '(empty)'}")
            return True, response

    # =========================================================================
    #                       ENHANCED API COMMANDS
    # =========================================================================

    @ensure_connection
    def send_message(self, message):
        """
        Send a global message to all players

        Args:
            message: Message to send

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.info(f"Sending global message: '{message}'")
        command = f'say -1 {message}'
        return self.send_command(command)

    @ensure_connection
    def send_private_message(self, player_id, message):
        """
        Send a private message to a specific player

        Args:
            player_id: Player ID
            message: Message to send

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.info(f"Sending PM to player ID {player_id}: '{message}'")
        command = f'say {player_id} {message}'
        return self.send_command(command)

    @ensure_connection
    def lock_server(self):
        """
        Lock the server - no one can join

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.warning("🔒 Locking server (#lock)")
        return self.send_command("#lock")

    @ensure_connection
    def unlock_server(self):
        """
        Unlock the server

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.warning("🔓 Unlocking server (#unlock)")
        return self.send_command("#unlock")

    @ensure_connection
    def kick_player(self, player_id, reason="Admin Kick"):
        """
        Kick a player from the server

        Args:
            player_id: Player ID to kick
            reason: Kick reason

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.info(f"🥾 Kicking player ID {player_id}. Reason: {reason}")
        return self.send_command(f'kick {player_id} {reason}')

    @ensure_connection
    def ban_player(self, player_id, minutes=0, reason="Banned"):
        """
        Ban a player

        Args:
            player_id: Player ID to ban
            minutes: Ban duration (0 = permanent)
            reason: Ban reason

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.info(f"⛔ Banning player ID {player_id} for {minutes} min. Reason: {reason}")
        return self.send_command(f'ban {player_id} {minutes} {reason}')

    @ensure_connection
    def shutdown_server(self):
        """
        Shutdown/restart the server via RCon

        Returns:
            tuple: (success: bool, response: str)
        """
        logger.critical("⚠️ SHUTDOWN COMMAND SENT!")
        return self.send_command("#shutdown")

    @ensure_connection
    def get_players(self):
        """
        Get list of online players

        Returns:
            tuple: (success: bool, players: list)
        """
        success, response = self.send_command('players', timeout=2.0)

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
                    p_id = parts[0]
                    # Only process if ID is a digit (actual player line)
                    if p_id.isdigit():
                        player = {
                            'id': p_id,
                            'ip': parts[1] if len(parts) > 1 else 'Unknown',
                            'ping': parts[2] if len(parts) > 2 else 'N/A',
                            'guid': parts[3] if len(parts) > 3 else 'N/A',
                            'name': parts[4] if len(parts) > 4 else 'Unknown'
                        }
                        players.append(player)

            return True, players
        except Exception as e:
            logger.error(f"Error parsing players: {str(e)}")
            return False, []

    @ensure_connection
    def kick_all_players(self, reason="Server Restart"):
        """
        Kick all players from the server

        Args:
            reason: Kick reason

        Returns:
            tuple: (success: bool, message: str)
        """
        success, players = self.get_players()

        if not success:
            return False, "Failed to get player list"

        kicked = 0
        for player in players:
            kick_success, _ = self.kick_player(player["id"], reason)
            if kick_success:
                kicked += 1
            time.sleep(0.2)  # Small delay between kicks

        return True, f"Kicked {kicked} player(s)"

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
        """
        Get an RCon connection for a server

        Args:
            server: GameServer instance

        Returns:
            BattlEyeRCon: RCon connection instance
        """
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
        """
        Test RCon connection

        Args:
            server: GameServer instance

        Returns:
            tuple: (success: bool, message: str, details: dict)
        """
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
        """
        Get list of online players

        Args:
            server: GameServer instance

        Returns:
            tuple: (success: bool, players: list, message: str)
        """
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
        """
        Send a message to all players

        Args:
            server: GameServer instance
            message: Message to send

        Returns:
            tuple: (success: bool, message: str)
        """
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
    def kick_all_players(server, reason="Server Restart"):
        """
        Kick all players

        Args:
            server: GameServer instance
            reason: Kick reason

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.kick_all_players(reason)

        except Exception as e:
            logger.error(f"Error kicking players: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def kick_player(server, player_id, reason="Admin Kick"):
        """
        Kick a specific player

        Args:
            server: GameServer instance
            player_id: Player ID to kick
            reason: Kick reason

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.kick_player(player_id, reason)

        except Exception as e:
            logger.error(f"Error kicking player: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def ban_player(server, player_id, minutes=0, reason="Banned"):
        """
        Ban a player

        Args:
            server: GameServer instance
            player_id: Player ID to ban
            minutes: Ban duration (0 = permanent)
            reason: Ban reason

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.ban_player(player_id, minutes, reason)

        except Exception as e:
            logger.error(f"Error banning player: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def lock_server(server):
        """
        Lock the server

        Args:
            server: GameServer instance

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.lock_server()

        except Exception as e:
            logger.error(f"Error locking server: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def unlock_server(server):
        """
        Unlock the server

        Args:
            server: GameServer instance

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.unlock_server()

        except Exception as e:
            logger.error(f"Error unlocking server: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def execute_command(server, command):
        """
        Execute a custom RCon command

        Args:
            server: GameServer instance
            command: Command to execute

        Returns:
            tuple: (success: bool, response: str)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()
                if not success:
                    return False, f"Failed to connect: {msg}"

                return rcon.send_command(command)

        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return False, f"Error: {str(e)}"
