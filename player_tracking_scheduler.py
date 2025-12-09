try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PlayerTrackingScheduler:
    """
    Background scheduler for player tracking
    - Monitors server logs for player join/leave events in real-time
    - Updates online players every 30 minutes
    """

    def __init__(self, app, server_manager):
        self.app = app
        self.server_manager = server_manager
        self.scheduler = None
        self.player_trackers = {}  # server_id -> PlayerTracker

        if APSCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            logger.info("Player Tracking Scheduler initialized")
        else:
            logger.warning("APScheduler not installed - Player tracking is disabled")
            logger.warning("Install with: pip install apscheduler")

    def initialize_trackers(self):
        """Initialize player trackers for all servers"""
        with self.app.app_context():
            try:
                from database import GameServer
                from player_tracker import PlayerTracker

                servers = GameServer.query.filter_by(is_installed=True).all()

                for server in servers:
                    try:
                        tracker = PlayerTracker(server)
                        # Log the log file path for debugging
                        logger.info(f"Player tracker for '{server.name}' will monitor: {tracker.log_parser.log_file_path}")

                        # Skip existing logs (start fresh from now)
                        tracker.log_parser.tail_to_end()

                        # Sync with RCon to detect currently online players
                        # This ensures players who joined BEFORE the tracker started are tracked
                        try:
                            if server.status == 'running':
                                synced = tracker.sync_with_rcon()
                                if synced > 0:
                                    logger.info(f"Synced {synced} currently online player(s) for '{server.name}'")
                        except Exception as e:
                            logger.warning(f"Could not sync with RCon for '{server.name}': {e}")

                        self.player_trackers[server.id] = tracker
                        logger.info(f"Initialized player tracker for server: {server.name}")
                    except Exception as e:
                        logger.error(f"Error initializing tracker for server {server.name}: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error initializing player trackers: {e}")

    def start_tracking(self):
        """Start all player tracking tasks"""
        if not APSCHEDULER_AVAILABLE or not self.scheduler:
            logger.warning("Cannot start player tracking - APScheduler not available")
            return

        # Initialize trackers
        self.initialize_trackers()

        # Task 1: Monitor logs for player events (every 10 seconds for real-time tracking)
        self.scheduler.add_job(
            func=self._monitor_player_events,
            trigger=IntervalTrigger(seconds=10),
            id='player_event_monitor',
            name='Monitor player join/leave events',
            replace_existing=True
        )
        logger.info("Player event monitoring started (every 10 seconds)")

        # Task 2: Update online players (every 30 minutes)
        self.scheduler.add_job(
            func=self._update_online_players,
            trigger=IntervalTrigger(minutes=30),
            id='player_online_update',
            name='Update online players every 30 minutes',
            replace_existing=True
        )
        logger.info("Online player update task started (every 30 minutes)")

    def _monitor_player_events(self):
        """Monitor server logs for player join/leave events"""
        with self.app.app_context():
            try:
                for server_id, tracker in self.player_trackers.items():
                    try:
                        # Debug: Log file path
                        logger.debug(f"Checking log file: {tracker.log_parser.log_file_path}")
                        tracker.process_log_events()
                    except Exception as e:
                        logger.error(f"Error processing log events for server {server_id}: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in player event monitor: {e}", exc_info=True)

    def _update_online_players(self):
        """Update all online players (called every 30 minutes)"""
        with self.app.app_context():
            try:
                logger.info("Running scheduled online player update...")

                for server_id, tracker in self.player_trackers.items():
                    try:
                        tracker.update_online_players()
                    except Exception as e:
                        logger.error(f"Error updating online players for server {server_id}: {e}")

                logger.info("Online player update completed")

            except Exception as e:
                logger.error(f"Error in online player update task: {e}")

    def get_tracker(self, server_id: int):
        """Get player tracker for a specific server"""
        return self.player_trackers.get(server_id)

    def add_server_tracker(self, server):
        """Add tracker for a new server"""
        try:
            from player_tracker import PlayerTracker

            tracker = PlayerTracker(server)
            tracker.log_parser.tail_to_end()  # Start from current position

            # Sync with RCon to detect currently online players
            try:
                if server.status == 'running':
                    synced = tracker.sync_with_rcon()
                    if synced > 0:
                        logger.info(f"Synced {synced} currently online player(s) for new server '{server.name}'")
            except Exception as e:
                logger.warning(f"Could not sync with RCon for new server '{server.name}': {e}")

            self.player_trackers[server.id] = tracker
            logger.info(f"Added player tracker for new server: {server.name}")
            return tracker
        except Exception as e:
            logger.error(f"Error adding tracker for server {server.name}: {e}")
            return None

    def remove_server_tracker(self, server_id: int):
        """Remove tracker for a deleted server"""
        if server_id in self.player_trackers:
            del self.player_trackers[server_id]
            logger.info(f"Removed player tracker for server ID: {server_id}")

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler and hasattr(self.scheduler, 'running') and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Player Tracking Scheduler shut down")
