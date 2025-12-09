"""
DayZ Server Ban Management
Manages ban.txt file for DayZ servers
"""
import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class BanManager:
    """Manage DayZ server bans via ban.txt"""

    def __init__(self, server):
        """
        Initialize BanManager for a server

        Args:
            server: GameServer instance
        """
        self.server = server
        self.ban_file_path = os.path.join(server.install_path, 'ban.txt')

    def _ensure_ban_file_exists(self):
        """Create ban.txt if it doesn't exist"""
        if not os.path.exists(self.ban_file_path):
            try:
                with open(self.ban_file_path, 'w') as f:
                    f.write("//Players added to the ban.txt won't be able to connect to this server.\n")
                    f.write("//Bans can be added/removed while the server is running and will come in effect immediately, kicking the player.\n")
                    f.write("//-----------------------------------------------------------------------------------------------------\n")
                    f.write("//To ban a player, add his player ID (44 characters long ID) which can be found in the admin log file (.ADM).\n")
                    f.write("//-----------------------------------------------------------------------------------------------------\n")
                    f.write("//For comments use the // prefix. It can be used after an inserted ID, to easily mark it.\n\n")
                logger.info(f"Created ban.txt at: {self.ban_file_path}")
            except Exception as e:
                logger.error(f"Error creating ban.txt: {e}")

    def get_banned_steam_ids(self) -> List[str]:
        """
        Read all banned Steam IDs from ban.txt

        Returns:
            list: List of banned Steam IDs
        """
        banned_ids = []

        if not os.path.exists(self.ban_file_path):
            logger.warning(f"ban.txt does not exist: {self.ban_file_path}")
            return banned_ids

        try:
            with open(self.ban_file_path, 'r') as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        continue

                    # Skip comment lines
                    if line.startswith('//'):
                        continue

                    # Extract Steam ID (before any comment)
                    if '//' in line:
                        steam_id = line.split('//')[0].strip()
                    else:
                        steam_id = line

                    # Validate Steam ID (should be numeric, 17 digits)
                    if steam_id and steam_id.isdigit() and len(steam_id) == 17:
                        banned_ids.append(steam_id)

            logger.debug(f"Read {len(banned_ids)} banned Steam IDs from ban.txt")
            return banned_ids

        except Exception as e:
            logger.error(f"Error reading ban.txt: {e}")
            return []

    def is_banned(self, steam_id: str) -> bool:
        """
        Check if a Steam ID is banned

        Args:
            steam_id: Steam ID to check

        Returns:
            bool: True if banned, False otherwise
        """
        if not steam_id:
            return False

        banned_ids = self.get_banned_steam_ids()
        return steam_id in banned_ids

    def add_ban(self, steam_id: str, reason: str = None) -> Tuple[bool, str]:
        """
        Add a Steam ID to the ban list

        Args:
            steam_id: Steam ID to ban
            reason: Optional ban reason

        Returns:
            tuple: (success: bool, message: str)
        """
        if not steam_id:
            return False, "No Steam ID provided"

        # Validate Steam ID
        if not steam_id.isdigit() or len(steam_id) != 17:
            return False, "Invalid Steam ID format (must be 17 digits)"

        # Check if already banned
        if self.is_banned(steam_id):
            return False, "Steam ID is already banned"

        try:
            # Ensure ban.txt exists
            self._ensure_ban_file_exists()

            # Add to ban.txt
            with open(self.ban_file_path, 'a') as f:
                if reason:
                    f.write(f"{steam_id} // {reason}\n")
                else:
                    f.write(f"{steam_id}\n")

            logger.info(f"Banned Steam ID: {steam_id} - Reason: {reason or 'No reason provided'}")
            return True, f"Successfully banned Steam ID: {steam_id}"

        except Exception as e:
            logger.error(f"Error adding ban: {e}")
            return False, f"Error: {str(e)}"

    def remove_ban(self, steam_id: str) -> Tuple[bool, str]:
        """
        Remove a Steam ID from the ban list

        Args:
            steam_id: Steam ID to unban

        Returns:
            tuple: (success: bool, message: str)
        """
        if not steam_id:
            return False, "No Steam ID provided"

        if not os.path.exists(self.ban_file_path):
            return False, "ban.txt does not exist"

        try:
            # Read all lines
            with open(self.ban_file_path, 'r') as f:
                lines = f.readlines()

            # Filter out the banned Steam ID
            new_lines = []
            found = False

            for line in lines:
                # Check if this line contains the Steam ID
                if steam_id in line and not line.strip().startswith('//'):
                    found = True
                    continue  # Skip this line (remove ban)
                new_lines.append(line)

            if not found:
                return False, "Steam ID not found in ban list"

            # Write back
            with open(self.ban_file_path, 'w') as f:
                f.writelines(new_lines)

            logger.info(f"Unbanned Steam ID: {steam_id}")
            return True, f"Successfully unbanned Steam ID: {steam_id}"

        except Exception as e:
            logger.error(f"Error removing ban: {e}")
            return False, f"Error: {str(e)}"

    def get_ban_count(self) -> int:
        """
        Get total number of banned Steam IDs

        Returns:
            int: Number of banned Steam IDs
        """
        return len(self.get_banned_steam_ids())
