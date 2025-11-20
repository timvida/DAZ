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
        Verify Steam credentials by attempting login via SteamCMD
        Returns: (success: bool, message: str)
        """
        if not self.is_available():
            return False, "SteamCMD not found on system"

        try:
            # SteamCMD login command
            # Format: steamcmd +login username password +quit
            cmd = [
                self.steamcmd_path,
                '+login', username, password,
                '+quit'
            ]

            # Run SteamCMD with increased timeout for first-time setup
            # First run downloads/updates SteamCMD itself
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                text=True,
                bufsize=1
            )

            # Wait up to 180 seconds (3 minutes) for SteamCMD
            stdout, _ = process.communicate(timeout=180)

            # Debug: Print full output (remove in production)
            print("=== SteamCMD Output ===")
            print(stdout)
            print("======================")

            # Check for success first - multiple patterns indicate successful login
            success_patterns = [
                "Logged in OK",
                "Logging in user",  # When you see "Logging in user 'name' to Steam Public...OK"
                "Waiting for user info...OK",  # This confirms full login
            ]

            # If we see "Logging in user" AND it ends with "OK", login was successful
            if any(pattern in stdout for pattern in success_patterns):
                # Make sure it's not a failed login
                if "to Steam Public...FAILED" not in stdout and "Logged in FAILED" not in stdout:
                    return True, "Steam credentials verified successfully! ✓"

            # Now check for specific error conditions

            # Two-Factor Authentication / Steam Guard
            if any(x in stdout for x in ["Two-factor", "Steam Guard", "GUARD:", "enter the auth code"]):
                return False, "2FA/Steam Guard is enabled. Please disable it or use a different account without 2FA."

            # Invalid credentials - check for FAILED login
            if any(x in stdout for x in ["Invalid Password", "Invalid password", "FAILED login", "Logged in FAILED", "to Steam Public...FAILED"]):
                return False, "Invalid Steam username or password. Please check your credentials."

            # Account doesn't exist
            if "no user with that login" in stdout.lower():
                return False, "Steam account not found. Please check the username."

            # Rate limiting
            if "rate limit" in stdout.lower() or "too many login failures" in stdout.lower():
                return False, "Too many login attempts. Please wait a few minutes and try again."

            # Connection issues (but ignore locale warnings)
            if ("Failed to connect" in stdout or "connection" in stdout.lower()) and "setlocale" not in stdout.lower():
                return False, "Could not connect to Steam servers. Please check your internet connection."

            # Timeout during login
            if "timed out" in stdout.lower():
                return False, "Steam login timed out. Please try again."

            # If we get here, check if login actually succeeded despite warnings
            # SteamCMD often shows warnings about locale but login still works
            if "Waiting for user info...OK" in stdout or "Loading Steam API...OK" in stdout:
                return True, "Steam credentials verified successfully! ✓"

            # Try to extract actual error message, but ignore locale/setlocale warnings
            error_lines = [
                line for line in stdout.split('\n')
                if ('error' in line.lower() or 'failed' in line.lower())
                and 'setlocale' not in line.lower()
                and 'WARNING' not in line
            ]
            if error_lines:
                return False, f"Steam verification failed: {error_lines[0][:100]}"

            return False, "Could not verify Steam credentials. Please check username and password and ensure the account is valid."

        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except:
                pass
            return False, "Verification timeout after 3 minutes. SteamCMD may be updating. Try 'Skip Verification' and test during server installation."

        except FileNotFoundError:
            return False, f"SteamCMD not found at: {self.steamcmd_path}"

        except Exception as e:
            return False, f"Verification error: {str(e)}"

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
