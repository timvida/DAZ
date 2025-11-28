import os
import glob
import shutil
from datetime import datetime
from database import db, ServerMod, GameServer, SteamAccount
from steam_utils import SteamCMDManager
from config import Config

class ModManager:
    """Manages server mods"""

    def __init__(self):
        self.steam_manager = SteamCMDManager()

    def scan_server_mods(self, server_id):
        """
        Scan server directory for @mod folders and sync with database
        Returns: (success: bool, message: str, mods_found: int)
        """
        server = GameServer.query.get(server_id)
        if not server:
            return False, "Server not found", 0

        try:
            # Find all @* folders in server install directory
            mod_pattern = os.path.join(server.install_path, "@*")
            mod_folders = glob.glob(mod_pattern)

            # Get existing mods from database
            existing_mods = {mod.mod_folder: mod for mod in ServerMod.query.filter_by(server_id=server_id).all()}

            mods_found = 0
            mods_updated = 0
            for mod_folder_path in mod_folders:
                if not os.path.isdir(mod_folder_path):
                    continue

                mod_folder = os.path.basename(mod_folder_path)

                # Calculate folder size
                folder_size = self._get_folder_size(mod_folder_path)

                # Update existing mod if it exists
                if mod_folder in existing_mods:
                    existing_mod = existing_mods[mod_folder]
                    # Update size if it's missing or changed
                    if existing_mod.file_size != folder_size:
                        existing_mod.file_size = folder_size
                        existing_mod.last_updated = datetime.utcnow()
                        mods_updated += 1
                    continue

                # Try to get mod name from mod.cpp
                mod_name = self._get_mod_display_name(mod_folder_path)
                if not mod_name:
                    mod_name = mod_folder[1:]  # Remove @ prefix

                # Create new mod entry
                new_mod = ServerMod(
                    server_id=server_id,
                    mod_name=mod_name,
                    mod_folder=mod_folder,
                    mod_type='client',
                    is_active=False,
                    file_size=folder_size,
                    last_updated=datetime.utcnow()
                )

                db.session.add(new_mod)
                mods_found += 1

            db.session.commit()

            # Build message
            if mods_found > 0 and mods_updated > 0:
                message = f"Scan complete. Found {mods_found} new mod(s), updated {mods_updated} mod(s)"
            elif mods_found > 0:
                message = f"Scan complete. Found {mods_found} new mod(s)"
            elif mods_updated > 0:
                message = f"Scan complete. Updated {mods_updated} mod(s)"
            else:
                message = "Scan complete. No changes detected"

            return True, message, mods_found

        except Exception as e:
            db.session.rollback()
            return False, f"Error scanning mods: {str(e)}", 0

    def _get_mod_display_name(self, mod_path):
        """Extract display name from mod.cpp"""
        import re
        mod_cpp_path = os.path.join(mod_path, "mod.cpp")
        if not os.path.exists(mod_cpp_path):
            return None

        try:
            with open(mod_cpp_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                match = re.search(r'name\s*=\s*"([^"]+)"', content, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except:
            pass

        return None

    def _get_folder_size(self, folder_path):
        """Calculate folder size in bytes"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size

    def get_server_mods(self, server_id):
        """Get all mods for a server"""
        return ServerMod.query.filter_by(server_id=server_id).all()

    def toggle_mod(self, mod_id, active, mod_type=None):
        """
        Enable/disable a mod
        Returns: (success: bool, message: str)
        """
        mod = ServerMod.query.get(mod_id)
        if not mod:
            return False, "Mod not found"

        try:
            mod.is_active = active
            if mod_type:
                mod.mod_type = mod_type

            db.session.commit()

            # Rebuild server start parameters
            self._rebuild_server_mod_params(mod.server_id)

            status = "enabled" if active else "disabled"
            return True, f"Mod {status} successfully"

        except Exception as e:
            db.session.rollback()
            return False, f"Error toggling mod: {str(e)}"

    def update_mod_type(self, mod_id, mod_type):
        """
        Update mod type (client/server)
        Returns: (success: bool, message: str)
        """
        if mod_type not in ['client', 'server']:
            return False, "Invalid mod type. Must be 'client' or 'server'"

        mod = ServerMod.query.get(mod_id)
        if not mod:
            return False, "Mod not found"

        try:
            mod.mod_type = mod_type
            db.session.commit()

            # Rebuild server start parameters
            self._rebuild_server_mod_params(mod.server_id)

            return True, f"Mod type updated to {mod_type}"

        except Exception as e:
            db.session.rollback()
            return False, f"Error updating mod type: {str(e)}"

    def add_workshop_mod(self, server_id, workshop_id):
        """
        Download and add a mod from Steam Workshop
        Returns: (success: bool, message: str)
        """
        server = GameServer.query.get(server_id)
        if not server:
            return False, "Server not found"

        # Get Steam credentials
        steam_account = SteamAccount.query.first()
        if not steam_account:
            return False, "Steam account not configured"

        try:
            # Download mod via SteamCMD
            success, message, mod_path = self.steam_manager.download_workshop_mod(
                workshop_id,
                server.install_path,
                steam_account.username,
                steam_account.password
            )

            if not success:
                return False, message

            # Get mod folder name
            mod_folder = os.path.basename(mod_path)
            mod_name = self._get_mod_display_name(mod_path)
            if not mod_name:
                mod_name = mod_folder[1:]

            # Copy mod keys to server
            server_keys_path = os.path.join(server.install_path, "keys")
            key_success, key_msg, keys_copied = self.steam_manager.copy_mod_keys(mod_path, server_keys_path)

            # Calculate folder size
            folder_size = self._get_folder_size(mod_path)

            # Add to database
            new_mod = ServerMod(
                server_id=server_id,
                mod_name=mod_name,
                mod_folder=mod_folder,
                workshop_id=str(workshop_id),
                mod_type='client',
                is_active=False,
                auto_update=True,  # Enable auto-update for workshop mods
                keys_copied=(keys_copied > 0),
                file_size=folder_size,
                last_updated=datetime.utcnow()
            )

            db.session.add(new_mod)
            db.session.commit()

            return True, f"Mod added successfully! {key_msg}"

        except Exception as e:
            db.session.rollback()
            return False, f"Error adding mod: {str(e)}"

    def remove_mod(self, mod_id, delete_files=True):
        """
        Remove a mod from server
        Returns: (success: bool, message: str)
        """
        mod = ServerMod.query.get(mod_id)
        if not mod:
            return False, "Mod not found"

        server = GameServer.query.get(mod.server_id)
        if not server:
            return False, "Server not found"

        try:
            # Delete mod files if requested
            if delete_files:
                mod_path = os.path.join(server.install_path, mod.mod_folder)
                if os.path.exists(mod_path):
                    shutil.rmtree(mod_path)

            # Remove from database
            db.session.delete(mod)
            db.session.commit()

            # Rebuild server start parameters
            self._rebuild_server_mod_params(server.id)

            return True, "Mod removed successfully"

        except Exception as e:
            db.session.rollback()
            return False, f"Error removing mod: {str(e)}"

    def update_mod(self, mod_id):
        """
        Update a workshop mod
        Returns: (success: bool, message: str)
        """
        mod = ServerMod.query.get(mod_id)
        if not mod:
            return False, "Mod not found"

        if not mod.workshop_id:
            return False, "Mod is not from Steam Workshop"

        server = GameServer.query.get(mod.server_id)
        if not server:
            return False, "Server not found"

        # Get Steam credentials
        steam_account = SteamAccount.query.first()
        if not steam_account:
            return False, "Steam account not configured"

        try:
            mod_path = os.path.join(server.install_path, mod.mod_folder)

            success, message, updated = self.steam_manager.update_workshop_mod(
                mod.workshop_id,
                mod_path,
                steam_account.username,
                steam_account.password
            )

            if success and updated:
                # Update database
                mod.last_updated = datetime.utcnow()
                mod.file_size = self._get_folder_size(mod_path)
                db.session.commit()

                # Copy keys again
                server_keys_path = os.path.join(server.install_path, "keys")
                self.steam_manager.copy_mod_keys(mod_path, server_keys_path)

                return True, "Mod updated successfully"
            else:
                return success, message

        except Exception as e:
            return False, f"Error updating mod: {str(e)}"

    def _rebuild_server_mod_params(self, server_id):
        """Rebuild -mod and -serverMod parameters for server"""
        server = GameServer.query.get(server_id)
        if not server:
            return

        # Get all active mods
        active_mods = ServerMod.query.filter_by(server_id=server_id, is_active=True).all()

        # Separate client and server mods
        client_mods = [mod.mod_folder for mod in active_mods if mod.mod_type == 'client']
        server_mods = [mod.mod_folder for mod in active_mods if mod.mod_type == 'server']

        # Build semicolon-separated strings
        server.mods = ';'.join(client_mods)
        server.server_mods = ';'.join(server_mods)

        db.session.commit()

    def update_all_mods(self):
        """
        Update all mods with auto_update enabled
        Used by auto-update background task
        Returns: (success: bool, message: str, updated_count: int)
        """
        # Get Steam credentials
        steam_account = SteamAccount.query.first()
        if not steam_account:
            return False, "Steam account not configured", 0

        # Get all mods with auto_update enabled and workshop_id
        mods_to_update = ServerMod.query.filter_by(auto_update=True).filter(ServerMod.workshop_id.isnot(None)).all()

        updated_count = 0
        errors = []

        for mod in mods_to_update:
            try:
                success, message = self.update_mod(mod.id)
                if success:
                    updated_count += 1
                else:
                    errors.append(f"{mod.mod_name}: {message}")
            except Exception as e:
                errors.append(f"{mod.mod_name}: {str(e)}")

        if errors:
            error_msg = "; ".join(errors[:3])  # Show first 3 errors
            return True, f"Updated {updated_count} mod(s) with {len(errors)} error(s): {error_msg}", updated_count
        else:
            return True, f"Updated {updated_count} mod(s) successfully", updated_count
