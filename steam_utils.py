import os
import subprocess
import re
from pathlib import Path
from config import Config

class SteamCMDManager:
    """Manages SteamCMD operations"""

    def __init__(self):
        self.steamcmd_path = self._find_steamcmd()

    def _find_steamcmd(self):
        """Find SteamCMD installation"""
        # Check configured paths
        if os.path.exists(Config.STEAMCMD_PATH):
            return Config.STEAMCMD_PATH
        if os.path.exists(Config.STEAMCMD_ALT_PATH):
            return Config.STEAMCMD_ALT_PATH

        # Check if steamcmd is in PATH
        try:
            result = subprocess.run(['which', 'steamcmd'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    def is_available(self):
        """Check if SteamCMD is available"""
        return self.steamcmd_path is not None

    def verify_credentials(self, username, password):
        """
        Verify Steam credentials
        Returns: (success: bool, message: str)
        """
        if not self.is_available():
            return False, "SteamCMD not found on system"

        try:
            # Create a temporary script to test login
            test_script = f"+login {username} {password} +quit"

            # Run SteamCMD
            process = subprocess.Popen(
                [self.steamcmd_path, test_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(timeout=30)
            output = stdout + stderr

            # Check for success indicators
            if "Logged in OK" in output or "Success" in output:
                return True, "Steam credentials verified successfully"

            # Check for common errors
            if "Two-factor" in output or "Steam Guard" in output or "GUARD" in output:
                return False, "2FA/Steam Guard is enabled. Please use an account without 2FA as recommended."

            if "Invalid Password" in output or "Invalid password" in output:
                return False, "Invalid username or password"

            if "rate limit" in output.lower():
                return False, "Steam rate limit reached. Please try again later."

            # Generic failure
            return False, "Could not verify Steam credentials. Please check username and password."

        except subprocess.TimeoutExpired:
            return False, "Connection timeout. Please try again."
        except Exception as e:
            return False, f"Error: {str(e)}"

    def install_server(self, app_id, install_dir, username, password, validate=True):
        """
        Install/Update a game server
        Returns: (success: bool, message: str)
        """
        if not self.is_available():
            return False, "SteamCMD not found on system"

        try:
            # Create install directory if it doesn't exist
            os.makedirs(install_dir, exist_ok=True)

            # Build SteamCMD command
            validate_flag = "validate" if validate else ""
            commands = [
                self.steamcmd_path,
                f"+force_install_dir {install_dir}",
                f"+login {username} {password}",
                f"+app_update {app_id} {validate_flag}",
                "+quit"
            ]

            # Run installation
            process = subprocess.Popen(
                commands,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(timeout=3600)  # 1 hour timeout
            output = stdout + stderr

            # Check for success
            if "Success" in output or "fully installed" in output:
                return True, "Server installed successfully"

            # Check for errors
            if "Invalid Password" in output:
                return False, "Invalid Steam credentials"

            if "No subscription" in output:
                return False, "Steam account doesn't own this game/app"

            return False, "Installation failed. Check logs for details."

        except subprocess.TimeoutExpired:
            return False, "Installation timeout. This may indicate a problem."
        except Exception as e:
            return False, f"Installation error: {str(e)}"

    def get_server_status(self, install_dir):
        """Check if server is installed and get basic info"""
        if not os.path.exists(install_dir):
            return {"installed": False, "size": 0}

        # Calculate directory size
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(install_dir):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)

        # Convert to GB
        size_gb = total_size / (1024 ** 3)

        return {
            "installed": True,
            "size": round(size_gb, 2),
            "path": install_dir
        }
