import os
import subprocess
import sys
from pathlib import Path
from config import Config

class UpdateManager:
    """Manages web interface updates from Git repository"""

    def __init__(self):
        self.repo_url = "https://github.com/timvida/DAZ.git"
        self.base_dir = Config.BASE_DIR
        self.is_git_repo = os.path.exists(os.path.join(self.base_dir, '.git'))

    def check_for_updates(self):
        """Check if updates are available from Git repository"""
        if not self.is_git_repo:
            return {
                'success': False,
                'message': 'Not a Git repository. Cannot check for updates.',
                'has_updates': False
            }

        try:
            # Fetch latest changes from remote
            subprocess.run(
                ['git', 'fetch', 'origin'],
                cwd=self.base_dir,
                check=True,
                capture_output=True,
                text=True
            )

            # Check if local is behind remote
            result = subprocess.run(
                ['git', 'rev-list', '--count', 'HEAD..origin/main'],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                check=True
            )

            commits_behind = int(result.stdout.strip())

            if commits_behind > 0:
                # Get commit messages
                log_result = subprocess.run(
                    ['git', 'log', '--oneline', 'HEAD..origin/main'],
                    cwd=self.base_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )

                return {
                    'success': True,
                    'has_updates': True,
                    'commits_behind': commits_behind,
                    'changes': log_result.stdout.strip(),
                    'message': f'{commits_behind} neue Update(s) verfügbar'
                }
            else:
                return {
                    'success': True,
                    'has_updates': False,
                    'commits_behind': 0,
                    'message': 'System ist auf dem neuesten Stand'
                }

        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'message': f'Fehler beim Prüfen auf Updates: {str(e)}',
                'has_updates': False
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Unerwarteter Fehler: {str(e)}',
                'has_updates': False
            }

    def perform_update(self):
        """Perform the actual update"""
        if not self.is_git_repo:
            return False, 'Not a Git repository. Cannot perform update.'

        try:
            # Check for local changes
            status_result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                check=True
            )

            # Stash local changes if any (except protected files)
            if status_result.stdout.strip():
                subprocess.run(
                    ['git', 'stash', 'push', '-u'],
                    cwd=self.base_dir,
                    check=True,
                    capture_output=True
                )

            # Pull latest changes
            pull_result = subprocess.run(
                ['git', 'pull', 'origin', 'main'],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                check=True
            )

            # Update Python dependencies
            self._update_dependencies()

            return True, 'Update erfolgreich! Webinterface wird neu gestartet...'

        except subprocess.CalledProcessError as e:
            return False, f'Fehler beim Update: {e.stderr if e.stderr else str(e)}'
        except Exception as e:
            return False, f'Unerwarteter Fehler beim Update: {str(e)}'

    def _update_dependencies(self):
        """Update Python dependencies from requirements.txt"""
        try:
            requirements_file = os.path.join(self.base_dir, 'requirements.txt')
            if os.path.exists(requirements_file):
                # Get path to venv pip
                venv_pip = os.path.join(self.base_dir, 'venv', 'bin', 'pip')

                if os.path.exists(venv_pip):
                    subprocess.run(
                        [venv_pip, 'install', '-r', requirements_file],
                        cwd=self.base_dir,
                        check=True,
                        capture_output=True
                    )
                else:
                    # Fallback to system pip3
                    subprocess.run(
                        ['pip3', 'install', '-r', requirements_file],
                        cwd=self.base_dir,
                        check=True,
                        capture_output=True
                    )
        except Exception as e:
            print(f"Warning: Could not update dependencies: {str(e)}")

    def restart_application(self):
        """Restart the web interface"""
        try:
            # This will cause the current process to restart
            # Note: This requires proper process management (systemd, supervisor, etc.)
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception as e:
            return False, f'Fehler beim Neustart: {str(e)}'

    def get_current_version(self):
        """Get current Git commit hash"""
        if not self.is_git_repo:
            return "Unknown"

        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except:
            return "Unknown"
