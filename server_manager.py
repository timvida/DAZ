import os
import subprocess
import signal
from pathlib import Path
from config import Config
from database import db, GameServer

class ServerManager:
    """Manages game server instances"""

    def __init__(self):
        self.servers_dir = Config.SERVERS_DIR
        os.makedirs(self.servers_dir, exist_ok=True)

    def create_server(self, name, game_name, app_id):
        """Create a new server entry"""
        # Generate install path
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        install_path = os.path.join(self.servers_dir, safe_name)

        # Create database entry
        server = GameServer(
            name=name,
            game_name=game_name,
            app_id=app_id,
            install_path=install_path,
            status='stopped',
            is_installed=False
        )

        db.session.add(server)
        db.session.commit()

        return server

    def get_server(self, server_id):
        """Get server by ID"""
        return GameServer.query.get(server_id)

    def get_all_servers(self):
        """Get all servers"""
        return GameServer.query.all()

    def delete_server(self, server_id):
        """Delete a server and its files"""
        server = self.get_server(server_id)
        if not server:
            return False, "Server not found"

        # Stop server if running
        if server.status == 'running':
            self.stop_server(server_id)

        # Delete files
        if os.path.exists(server.install_path):
            try:
                import shutil
                shutil.rmtree(server.install_path)
            except Exception as e:
                return False, f"Could not delete server files: {str(e)}"

        # Delete from database
        db.session.delete(server)
        db.session.commit()

        return True, "Server deleted successfully"

    def start_server(self, server_id):
        """Start a game server"""
        server = self.get_server(server_id)
        if not server:
            return False, "Server not found"

        if not server.is_installed:
            return False, "Server is not installed"

        if server.status == 'running':
            return False, "Server is already running"

        try:
            # Find server executable based on game
            executable = self._find_server_executable(server)
            if not executable:
                return False, "Server executable not found"

            # Start server process (simplified - would need game-specific logic)
            # This is a placeholder - actual implementation would vary by game
            server.status = 'running'
            db.session.commit()

            return True, "Server started successfully"

        except Exception as e:
            return False, f"Error starting server: {str(e)}"

    def stop_server(self, server_id):
        """Stop a game server"""
        server = self.get_server(server_id)
        if not server:
            return False, "Server not found"

        if server.status != 'running':
            return False, "Server is not running"

        try:
            # Stop server process (simplified)
            server.status = 'stopped'
            db.session.commit()

            return True, "Server stopped successfully"

        except Exception as e:
            return False, f"Error stopping server: {str(e)}"

    def _find_server_executable(self, server):
        """Find the server executable for a game"""
        # Game-specific executable names
        executables = {
            "DayZ": ["DayZServer"],
            "Rust": ["RustDedicated"],
            "ARK": ["ShooterGameServer"],
        }

        exe_names = executables.get(server.game_name, [])

        for exe_name in exe_names:
            # Check Linux executable
            exe_path = os.path.join(server.install_path, exe_name)
            if os.path.exists(exe_path):
                return exe_path

            # Check in common subdirectories
            for subdir in ['', 'bin', 'Binaries/Linux']:
                exe_path = os.path.join(server.install_path, subdir, exe_name)
                if os.path.exists(exe_path):
                    return exe_path

        return None

    def update_server_status(self, server_id, status):
        """Update server status"""
        server = self.get_server(server_id)
        if server:
            server.status = status
            db.session.commit()
            return True
        return False

    def mark_server_installed(self, server_id):
        """Mark server as installed"""
        server = self.get_server(server_id)
        if server:
            server.is_installed = True
            server.status = 'stopped'
            db.session.commit()
            return True
        return False
