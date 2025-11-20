import os
import subprocess
import signal
import multiprocessing
from pathlib import Path
from config import Config
from database import db, GameServer

class ServerManager:
    """Manages game server instances"""

    def __init__(self):
        self.servers_dir = Config.SERVERS_DIR
        os.makedirs(self.servers_dir, exist_ok=True)

    def create_server(self, name, game_name, app_id, server_port=2302, rcon_port=2306, rcon_password=None):
        """Create a new server entry"""
        # Generate install path
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        install_path = os.path.join(self.servers_dir, safe_name)

        # Detect available CPU cores
        cpu_count = self._detect_cpu_count()

        # Generate profile and BattlEye paths for DayZ
        profile_path = os.path.join(install_path, 'profiles')
        be_path = os.path.join(profile_path, 'BattlEye')

        # Create database entry
        server = GameServer(
            name=name,
            game_name=game_name,
            app_id=app_id,
            install_path=install_path,
            server_port=server_port,
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            cpu_count=cpu_count,
            profile_path=profile_path,
            be_path=be_path,
            status='stopped',
            is_installed=False
        )

        db.session.add(server)
        db.session.commit()

        # Create profile and BattlEye directories
        os.makedirs(profile_path, exist_ok=True)
        os.makedirs(be_path, exist_ok=True)

        return server

    def _detect_cpu_count(self):
        """Detect available CPU cores for server allocation"""
        try:
            total_cores = multiprocessing.cpu_count()
            # Allocate all cores but leave at least 2 for the system if available
            if total_cores > 4:
                return total_cores - 2
            elif total_cores > 2:
                return total_cores - 1
            else:
                return total_cores
        except:
            return 2  # Default fallback

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
        """Start a DayZ server"""
        server = self.get_server(server_id)
        if not server:
            return False, "Server not found"

        if not server.is_installed:
            return False, "Server is not installed"

        if server.status == 'running':
            return False, "Server is already running"

        try:
            # Find DayZ server executable
            executable = self._find_server_executable(server)
            if not executable:
                return False, "DayZ Server executable not found"

            # Make sure executable has execute permissions
            os.chmod(executable, 0o755)

            # Prepare DayZ start command with all parameters
            cmd = [
                executable,
                f'-config=serverDZ.cfg',
                f'-port={server.server_port}',
                f'-profiles={server.profile_path}',
                f'-BEpath={server.be_path}',
                f'-cpuCount={server.cpu_count}'
            ]

            # Add mod parameters if they exist
            if server.mods and server.mods.strip():
                cmd.append(f'-mod={server.mods}')

            if server.server_mods and server.server_mods.strip():
                cmd.append(f'-serverMod={server.server_mods}')

            # Create log directory
            log_dir = os.path.join(server.profile_path, 'logs')
            os.makedirs(log_dir, exist_ok=True)

            # Create log files for stdout and stderr
            stdout_log = os.path.join(log_dir, 'server_stdout.log')
            stderr_log = os.path.join(log_dir, 'server_stderr.log')

            # Start the server process
            with open(stdout_log, 'a') as stdout_file, open(stderr_log, 'a') as stderr_file:
                process = subprocess.Popen(
                    cmd,
                    cwd=server.install_path,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    preexec_fn=os.setsid  # Create new process group for clean shutdown
                )

            # Update server status and save process ID
            server.status = 'running'
            server.process_id = process.pid
            db.session.commit()

            return True, f"DayZ Server started successfully (PID: {process.pid})"

        except Exception as e:
            return False, f"Error starting server: {str(e)}"

    def stop_server(self, server_id):
        """Stop a DayZ server"""
        server = self.get_server(server_id)
        if not server:
            return False, "Server not found"

        if server.status != 'running':
            return False, "Server is not running"

        try:
            # Check if we have a process ID
            if server.process_id:
                try:
                    # Try to check if process is still running
                    os.kill(server.process_id, 0)  # Signal 0 checks existence

                    # Process exists, send SIGTERM for graceful shutdown
                    os.killpg(os.getpgid(server.process_id), signal.SIGTERM)

                    # Wait a bit for graceful shutdown
                    import time
                    time.sleep(2)

                    # Check if process is still running
                    try:
                        os.kill(server.process_id, 0)
                        # Still running, force kill
                        os.killpg(os.getpgid(server.process_id), signal.SIGKILL)
                    except ProcessLookupError:
                        # Process already terminated
                        pass

                except ProcessLookupError:
                    # Process doesn't exist anymore
                    pass
                except Exception as e:
                    # Log error but continue with status update
                    print(f"Error stopping process: {str(e)}")

            # Update server status
            server.status = 'stopped'
            server.process_id = None
            db.session.commit()

            return True, "DayZ Server stopped successfully"

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
        """Mark server as installed and create configuration files"""
        server = self.get_server(server_id)
        if server:
            server.is_installed = True
            server.status = 'stopped'
            db.session.commit()

            # Create serverDZ.cfg if it doesn't exist
            self._create_server_config(server)

            return True
        return False

    def _create_server_config(self, server):
        """Create default serverDZ.cfg file for DayZ server"""
        config_path = os.path.join(server.install_path, 'serverDZ.cfg')

        # Don't overwrite existing config
        if os.path.exists(config_path):
            return

        config_content = f"""// {server.name} - DayZ Server Configuration
// Auto-generated by GameServer Manager

hostname = "{server.name}";
password = "";
passwordAdmin = "{server.rcon_password}";

maxPlayers = 60;

verifySignatures = 2;
forceSameBuild = 1;
disableVoN = 0;
vonCodecQuality = 20;

disable3rdPerson = 0;
disableCrosshair = 0;

serverTime = "SystemTime";
serverTimeAcceleration = 6;
serverNightTimeAcceleration = 4;

guaranteedUpdates = 1;

loginQueueConcurrentPlayers = 5;
loginQueueMaxPlayers = 500;

instanceId = 1;

storageAutoFix = 1;

respawnTime = 5;

motd[] = {{"Welcome to {server.name}"}};
motdInterval = 1;

timeStampFormat = "Short";

logAverageFps = 1;
logMemory = 1;
logPlayers = 1;
logFile = "server_console.log";

enableDebugMonitor = 0;

steamQueryPort = {server.server_port + 2};

class Missions
{{
    class DayZ
    {{
        template = "dayzOffline.chernarusplus";
    }};
}};
"""

        try:
            with open(config_path, 'w') as f:
                f.write(config_content)
            print(f"Created serverDZ.cfg at {config_path}")
        except Exception as e:
            print(f"Error creating serverDZ.cfg: {str(e)}")
