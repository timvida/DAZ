try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServerUpdateScheduler:
    """Background scheduler for automatic DayZ server update checks"""

    def __init__(self, app, steam_manager, server_manager):
        self.app = app
        self.steam_manager = steam_manager
        self.server_manager = server_manager
        self.scheduler = None

        if APSCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            logger.info("Server Update Scheduler initialized")
        else:
            logger.warning("APScheduler not installed - Auto-update check for servers is disabled")
            logger.warning("Install with: pip install apscheduler")

    def start_auto_update_check(self):
        """Start the auto-update check task (runs every 4 hours = 240 minutes)"""
        if not APSCHEDULER_AVAILABLE or not self.scheduler:
            logger.warning("Cannot start auto-update check task - APScheduler not available")
            return

        self.scheduler.add_job(
            func=self._check_server_updates_task,
            trigger=IntervalTrigger(minutes=240),  # Every 4 hours
            id='server_auto_update_check',
            name='Check for DayZ server updates every 4 hours',
            replace_existing=True
        )
        logger.info("Server auto-update check task scheduled (every 4 hours)")

    def _check_server_updates_task(self):
        """Background task to check all servers for available updates"""
        with self.app.app_context():
            try:
                from database import db, GameServer, SteamAccount

                logger.info("Starting server update check task...")

                # Get Steam credentials
                steam_account = SteamAccount.query.first()
                if not steam_account:
                    logger.error("No Steam account configured - cannot check for updates")
                    return

                # Get all installed servers
                servers = GameServer.query.filter_by(is_installed=True).all()

                if not servers:
                    logger.info("No installed servers found to check for updates")
                    return

                logger.info(f"Checking {len(servers)} server(s) for updates...")

                checked_count = 0
                updated_count = 0
                error_count = 0

                for server in servers:
                    try:
                        logger.info(f"Checking server: {server.name} (ID: {server.id})")

                        # Check for updates
                        update_available, message = self.steam_manager.check_for_server_update(
                            server.app_id,
                            server.install_path,
                            steam_account.username,
                            steam_account.password
                        )

                        # Update the database
                        server.last_update_check = datetime.utcnow()

                        if update_available:
                            logger.info(f"Update available for {server.name}: {message}")
                            server.update_available = True
                            server.update_downloaded = True  # The check_for_server_update already downloads it
                            updated_count += 1
                        else:
                            logger.info(f"No update for {server.name}: {message}")
                            server.update_available = False
                            server.update_downloaded = False

                        checked_count += 1
                        db.session.commit()

                    except Exception as e:
                        logger.error(f"Error checking server {server.name}: {str(e)}")
                        error_count += 1
                        continue

                logger.info(f"Update check completed: {checked_count} checked, {updated_count} updates found, {error_count} errors")

            except Exception as e:
                logger.error(f"Error in server update check task: {str(e)}")

    def check_single_server_update(self, server_id):
        """
        Manually check a single server for updates
        Returns: (success: bool, message: str, update_available: bool)
        """
        try:
            from database import db, GameServer, SteamAccount

            # Get the server
            server = GameServer.query.get(server_id)
            if not server:
                return False, "Server not found", False

            if not server.is_installed:
                return False, "Server is not installed", False

            # Get Steam credentials
            steam_account = SteamAccount.query.first()
            if not steam_account:
                return False, "No Steam account configured", False

            logger.info(f"Manual update check for server: {server.name} (ID: {server.id})")

            # Check for updates
            update_available, message = self.steam_manager.check_for_server_update(
                server.app_id,
                server.install_path,
                steam_account.username,
                steam_account.password
            )

            # Update the database
            server.last_update_check = datetime.utcnow()

            if update_available:
                server.update_available = True
                server.update_downloaded = True
                db.session.commit()
                return True, f"Update available and downloaded: {message}", True
            else:
                server.update_available = False
                server.update_downloaded = False
                db.session.commit()
                return True, message, False

        except Exception as e:
            logger.error(f"Error in manual update check: {str(e)}")
            return False, f"Error checking for updates: {str(e)}", False

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler and hasattr(self.scheduler, 'running') and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Server Update Scheduler shut down")
