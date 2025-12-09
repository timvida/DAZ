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

    def download_workshop_mod(self, workshop_id, install_dir, username, password):
        """
        Download a mod from Steam Workshop
        Returns: (success: bool, message: str, mod_path: str)
        """
        if not self.is_available():
            return False, "SteamCMD not found on system", None

        try:
            # DayZ Workshop App ID is 221100
            dayz_app_id = "221100"

            # Build SteamCMD command for workshop download
            # IMPORTANT: Each +command must be a separate argument
            commands = [
                self.steamcmd_path,
                "+login", username, password,
                "+workshop_download_item", dayz_app_id, workshop_id,
                "+quit"
            ]

            print(f"Downloading workshop mod {workshop_id} via SteamCMD...")
            print(f"Command: {' '.join(commands)}")

            # Run download
            process = subprocess.Popen(
                commands,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(timeout=1800)  # 30 minute timeout
            output = stdout + stderr

            print(f"=== SteamCMD Workshop Download Output ===")
            print(output)
            print("=========================================")

            # Check for success
            if "Success" in output or "Download complete" in output or f"Downloaded item {workshop_id}" in output:
                # Find the downloaded mod in steamcmd workshop folder
                # Try multiple possible locations
                possible_paths = []

                # 1. Based on steamcmd binary location
                if self.steamcmd_path:
                    steamcmd_dir = os.path.dirname(self.steamcmd_path)
                    possible_paths.append(os.path.join(steamcmd_dir, "steamapps", "workshop", "content", dayz_app_id, workshop_id))

                # 2. User home directory (from install.sh)
                home_dir = os.path.expanduser("~")
                possible_paths.append(os.path.join(home_dir, "steamcmd", "steamapps", "workshop", "content", dayz_app_id, workshop_id))

                # 3. Common locations
                possible_paths.append(os.path.join("/home", os.environ.get('USER', 'user'), "steamcmd", "steamapps", "workshop", "content", dayz_app_id, workshop_id))
                possible_paths.append(os.path.join("/opt", "steamcmd", "steamapps", "workshop", "content", dayz_app_id, workshop_id))

                # 4. Search using find command as fallback
                workshop_mod_path = None
                for path in possible_paths:
                    print(f"Checking path: {path}")
                    if os.path.exists(path):
                        workshop_mod_path = path
                        print(f"Found mod at: {workshop_mod_path}")
                        break

                # If still not found, use find command
                if not workshop_mod_path:
                    print(f"Mod not found in standard locations, searching...")
                    try:
                        import subprocess as sp
                        # Search for the workshop_id directory
                        find_result = sp.run(
                            ['find', home_dir, '-type', 'd', '-name', workshop_id, '-path', '*/steamapps/workshop/content/*'],
                            capture_output=True, text=True, timeout=10
                        )
                        if find_result.returncode == 0 and find_result.stdout.strip():
                            workshop_mod_path = find_result.stdout.strip().split('\n')[0]
                            print(f"Found mod via search: {workshop_mod_path}")
                    except Exception as e:
                        print(f"Search failed: {e}")

                if workshop_mod_path and os.path.exists(workshop_mod_path):
                    # Move/copy to server install directory
                    # We need to find the mod.cpp to get the mod name
                    mod_name = self._get_mod_name_from_path(workshop_mod_path)
                    if not mod_name:
                        mod_name = f"mod_{workshop_id}"

                    # Create @ModName folder in server directory
                    mod_folder = f"@{mod_name}"
                    target_path = os.path.join(install_dir, mod_folder)

                    # Copy mod files to server directory
                    import shutil
                    if os.path.exists(target_path):
                        shutil.rmtree(target_path)
                    shutil.copytree(workshop_mod_path, target_path)

                    return True, f"Mod downloaded successfully to {mod_folder}", target_path
                else:
                    # Show all checked paths in error message
                    paths_checked = "\n".join(possible_paths)
                    return False, f"Mod downloaded but not found. Checked locations:\n{paths_checked}", None

            # Check for errors
            if "Invalid Password" in output or "Invalid credentials" in output:
                return False, "Invalid Steam credentials", None

            if "No subscription" in output:
                return False, "Item not found or not subscribed", None

            if "ERROR" in output or "failed" in output.lower():
                # Extract error message
                error_lines = [line for line in output.split('\n') if 'error' in line.lower() or 'failed' in line.lower()]
                if error_lines:
                    return False, f"Download failed: {error_lines[0][:100]}", None

            return False, "Download failed. Check logs for details.", None

        except subprocess.TimeoutExpired:
            return False, "Download timeout after 30 minutes.", None
        except Exception as e:
            return False, f"Download error: {str(e)}", None

    def _get_mod_name_from_path(self, mod_path):
        """Extract mod name from mod.cpp file"""
        mod_cpp_path = os.path.join(mod_path, "mod.cpp")
        if not os.path.exists(mod_cpp_path):
            return None

        try:
            with open(mod_cpp_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Look for name = "ModName";
                match = re.search(r'name\s*=\s*"([^"]+)"', content, re.IGNORECASE)
                if match:
                    mod_name = match.group(1).strip()
                    # Remove special characters
                    mod_name = re.sub(r'[^\w\s-]', '', mod_name).strip()
                    mod_name = re.sub(r'[\s]+', '_', mod_name)
                    return mod_name
        except Exception as e:
            print(f"Error reading mod.cpp: {e}")

        return None

    def update_workshop_mod(self, workshop_id, mod_path, username, password):
        """
        Update a workshop mod (re-download)
        Returns: (success: bool, message: str, updated: bool)
        """
        # Get the server install dir from mod path
        # mod_path is like /servers/MyServer/@ModName
        install_dir = os.path.dirname(mod_path)

        success, message, new_path = self.download_workshop_mod(workshop_id, install_dir, username, password)

        if success:
            return True, "Mod updated successfully", True
        else:
            return False, message, False

    def copy_mod_keys(self, mod_path, server_keys_path):
        """
        Copy mod keys from @ModName/Keys to server/keys directory
        Returns: (success: bool, message: str, keys_copied: int)
        """
        try:
            # Find keys directory in mod
            mod_keys_path = os.path.join(mod_path, "Keys")
            if not os.path.exists(mod_keys_path):
                mod_keys_path = os.path.join(mod_path, "keys")

            if not os.path.exists(mod_keys_path):
                return True, "No keys directory found in mod (not required)", 0

            # Create server keys directory if it doesn't exist
            os.makedirs(server_keys_path, exist_ok=True)

            # Copy all .bikey files
            import shutil
            keys_copied = 0
            for filename in os.listdir(mod_keys_path):
                if filename.endswith('.bikey'):
                    src = os.path.join(mod_keys_path, filename)
                    dst = os.path.join(server_keys_path, filename)
                    shutil.copy2(src, dst)
                    keys_copied += 1
                    print(f"Copied key: {filename}")

            if keys_copied > 0:
                return True, f"Copied {keys_copied} key(s) successfully", keys_copied
            else:
                return True, "No .bikey files found in mod keys directory", 0

        except Exception as e:
            return False, f"Error copying keys: {str(e)}", 0

    def check_for_server_update(self, app_id, install_dir, username, password):
        """
        Check if a server update is available via SteamCMD
        This uses SteamCMD's app_update command in validate mode to check for updates
        Returns: (update_available: bool, message: str)
        """
        if not self.is_available():
            return False, "SteamCMD not found on system"

        try:
            # Build SteamCMD command to check for updates
            # We use validate to check if files need updating
            commands = [
                self.steamcmd_path,
                f"+force_install_dir {install_dir}",
                f"+login {username} {password}",
                f"+app_update {app_id} validate",
                "+quit"
            ]

            print(f"Checking for updates for App ID {app_id}...")

            # Run SteamCMD
            process = subprocess.Popen(
                commands,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(timeout=600)  # 10 minute timeout
            output = stdout + stderr

            # Debug output
            print(f"=== SteamCMD Update Check Output ===")
            print(output)
            print("====================================")

            # Check if update was needed and applied
            # SteamCMD will download files if they're out of date
            if "Success! App" in output and "fully installed" in output:
                # Check if files were actually updated
                if "downloading" in output.lower() or "update" in output.lower():
                    return True, "Update was available and has been downloaded"
                else:
                    return False, "Server is up to date"

            # Check for specific update-related messages
            if "Update state" in output or "Downloading" in output:
                return True, "Update detected and downloaded"

            # If validation succeeded without downloads, we're up to date
            if "Success" in output:
                return False, "Server is up to date"

            # Check for errors
            if "Invalid Password" in output or "Invalid credentials" in output:
                return False, "Invalid Steam credentials"

            if "No subscription" in output:
                return False, "Steam account doesn't own this game/app"

            return False, f"Unable to determine update status"

        except subprocess.TimeoutExpired:
            return False, "Update check timeout after 10 minutes"
        except Exception as e:
            return False, f"Error checking for updates: {str(e)}"

    def download_server_update(self, app_id, install_dir, username, password):
        """
        Download server update (same as install_server but specifically for updates)
        Returns: (success: bool, message: str)
        """
        # This is essentially the same as install_server with validate
        return self.install_server(app_id, install_dir, username, password, validate=True)
