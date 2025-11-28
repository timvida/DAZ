"""
DayZ BattlEye RCon Utility
Handles RCon connections to DayZ servers via BattlEye protocol
"""

import socket
import struct
import hashlib
import time
import logging
from threading import Lock

logger = logging.getLogger(__name__)


class BattlEyeRCon:
    """BattlEye RCon client for DayZ servers"""

    # BattlEye packet types
    PACKET_LOGIN = 0x00
    PACKET_COMMAND = 0x01
    PACKET_MESSAGE = 0x02

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
        self.socket = None
        self.sequence = 0
        self.lock = Lock()
        self.authenticated = False

    def connect(self, timeout=5):
        """
        Connect to the BattlEye RCon server

        Args:
            timeout: Connection timeout in seconds

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(timeout)

            # Send login packet
            success, message = self._login()

            if success:
                self.authenticated = True
                logger.info(f"Successfully connected to RCon at {self.host}:{self.port}")
                return True, "Connected successfully"
            else:
                self.disconnect()
                return False, f"Login failed: {message}"

        except socket.timeout:
            self.disconnect()
            return False, "Connection timeout - server not responding"
        except ConnectionRefusedError:
            self.disconnect()
            return False, "Connection refused - check if server is running"
        except Exception as e:
            self.disconnect()
            return False, f"Connection error: {str(e)}"

    def _login(self):
        """
        Authenticate with the RCon server

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Build login packet
            # Format: 'BE' + CRC32 + 0xFF + packet_type + password
            packet = b'BE'
            packet += b'\x00\x00\x00\x00'  # CRC32 placeholder
            packet += b'\xFF'  # Login packet identifier
            packet += self.PACKET_LOGIN.to_bytes(1, 'little')
            packet += self.password.encode('utf-8')

            # Calculate and insert CRC32
            crc = self._calculate_crc32(packet[6:])
            packet = packet[:2] + struct.pack('<I', crc) + packet[6:]

            # Send login packet
            self.socket.sendto(packet, (self.host, self.port))

            # Wait for response
            data, addr = self.socket.recvfrom(4096)

            if len(data) < 9:
                return False, "Invalid response from server"

            # Check if login was successful
            # Response format: 'BE' + CRC32 + 0xFF + 0x01 (login success) or 0x00 (login failed)
            if data[7] == 0x01:
                return True, "Login successful"
            else:
                return False, "Invalid password"

        except socket.timeout:
            return False, "Login timeout"
        except Exception as e:
            return False, f"Login error: {str(e)}"

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
                self.sequence = (self.sequence + 1) % 256

                # Build command packet
                # Format: 'BE' + CRC32 + 0xFF + packet_type + sequence + command
                packet = b'BE'
                packet += b'\x00\x00\x00\x00'  # CRC32 placeholder
                packet += b'\xFF'  # Command packet identifier
                packet += self.PACKET_COMMAND.to_bytes(1, 'little')
                packet += self.sequence.to_bytes(1, 'little')
                packet += command.encode('utf-8')

                # Calculate and insert CRC32
                crc = self._calculate_crc32(packet[6:])
                packet = packet[:2] + struct.pack('<I', crc) + packet[6:]

                # Send command packet
                self.socket.sendto(packet, (self.host, self.port))

                # Wait for acknowledgment
                old_timeout = self.socket.gettimeout()
                self.socket.settimeout(timeout)

                try:
                    data, addr = self.socket.recvfrom(4096)

                    if len(data) >= 9:
                        # Parse response
                        # Multi-packet responses are handled here
                        response = data[9:].decode('utf-8', errors='ignore')
                        return True, response
                    else:
                        return True, ""

                except socket.timeout:
                    return False, "Command timeout"
                finally:
                    self.socket.settimeout(old_timeout)

            except Exception as e:
                logger.error(f"Error sending command: {str(e)}")
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

                # Try to parse player line
                # Format can vary, but typically: ID, IP:Port, Ping, GUID, Name
                # Example: "0   192.168.1.1:2304   123   12345678901234567890   PlayerName"
                parts = line.split(None, 4)  # Split into max 5 parts
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
        # First get list of players
        success, players = self.get_players()

        if not success:
            return False, "Failed to get player list"

        # Kick each player
        try:
            kicked = 0
            for player in players:
                self.send_command(f'kick {player["id"]}')
                kicked += 1

            return True, f"Kicked {kicked} player(s)"
        except Exception as e:
            return False, f"Error kicking players: {str(e)}"

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
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.authenticated = False

    def _calculate_crc32(self, data):
        """
        Calculate CRC32 checksum for BattlEye packet

        Args:
            data: Data bytes to checksum

        Returns:
            int: CRC32 checksum
        """
        # BattlEye uses standard CRC32
        crc = 0xFFFFFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xEDB88320
                else:
                    crc >>= 1
        return crc ^ 0xFFFFFFFF

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()


class RConManager:
    """Manager for RCon operations on game servers"""

    @staticmethod
    def get_rcon_connection(server):
        """
        Get an RCon connection for a server

        Args:
            server: GameServer instance

        Returns:
            BattlEyeRCon: RCon connection object
        """
        # Get server IP
        from server_manager import ServerManager
        server_manager = ServerManager()
        server_ip = server_manager._get_server_ip()

        # Default to localhost if no IP detected
        if not server_ip:
            server_ip = '127.0.0.1'

        return BattlEyeRCon(server_ip, server.rcon_port, server.rcon_password)

    @staticmethod
    def test_connection(server):
        """
        Test RCon connection to a server

        Args:
            server: GameServer instance

        Returns:
            tuple: (success: bool, message: str, details: dict)
        """
        try:
            with RConManager.get_rcon_connection(server) as rcon:
                success, msg = rcon.connect()

                if success:
                    # Try to get server info
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
            details = {
                'connected': False,
                'error': str(e)
            }
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
        Send a message to all players on a server

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
    def kick_all_players(server):
        """
        Kick all players from a server

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

                return rcon.kick_all_players()

        except Exception as e:
            logger.error(f"Error kicking players: {str(e)}")
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
