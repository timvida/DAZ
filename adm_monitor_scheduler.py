"""
ADM Log Monitor Scheduler
Background task to monitor ADM logs for player events
"""
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ADMMonitorScheduler:
    """
    Background scheduler for ADM log monitoring
    - Monitors ADM logs for player events every 15 seconds
    - Sends Discord webhooks for configured events
    """

    def __init__(self, app, server_manager):
        self.app = app
        self.server_manager = server_manager
        self.scheduler = None
        self.adm_parsers = {}  # server_id -> ADMLogParser
        self.event_processors = {}  # server_id -> EventProcessor

        if APSCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            logger.info("ADM Monitor Scheduler initialized")
        else:
            logger.warning("APScheduler not installed - ADM monitoring is disabled")
            logger.warning("Install with: pip install apscheduler")

    def initialize_monitors(self):
        """Initialize ADM monitors for all servers"""
        with self.app.app_context():
            try:
                from database import GameServer
                from adm_log_parser import ADMLogParser
                from event_processor import EventProcessor

                servers = GameServer.query.filter_by(is_installed=True).all()

                for server in servers:
                    try:
                        # Initialize ADM parser
                        parser = ADMLogParser(server.profile_path)

                        # Find and tail to end of current log
                        latest_log = parser.find_latest_adm_log()
                        if latest_log:
                            logger.info(f"ADM monitor for '{server.name}' will monitor: {latest_log}")
                            parser.tail_to_end()
                        else:
                            logger.warning(f"No ADM log found for '{server.name}' at: {server.profile_path}")

                        # Initialize event processor
                        processor = EventProcessor(server)

                        self.adm_parsers[server.id] = parser
                        self.event_processors[server.id] = processor

                        logger.info(f"Initialized ADM monitor for server: {server.name}")
                    except Exception as e:
                        logger.error(f"Error initializing ADM monitor for server {server.name}: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error initializing ADM monitors: {e}")

    def start_monitoring(self):
        """Start ADM log monitoring task"""
        if not APSCHEDULER_AVAILABLE or not self.scheduler:
            logger.warning("Cannot start ADM monitoring - APScheduler not available")
            return

        # Initialize monitors
        self.initialize_monitors()

        # Task: Monitor ADM logs for events (every 15 seconds)
        self.scheduler.add_job(
            func=self._monitor_adm_logs,
            trigger=IntervalTrigger(seconds=15),
            id='adm_log_monitor',
            name='Monitor ADM logs for player events',
            replace_existing=True
        )
        logger.info("ADM log monitoring started (every 15 seconds)")

    def _monitor_adm_logs(self):
        """Monitor ADM logs for player events"""
        with self.app.app_context():
            try:
                from player_event_models import WebhookConfig
                from player_models import Player
                from discord_webhook import DiscordWebhook

                for server_id, parser in self.adm_parsers.items():
                    try:
                        # Read new events from ADM log
                        events = parser.read_new_lines()

                        if not events:
                            continue

                        # Get event processor
                        processor = self.event_processors.get(server_id)
                        if not processor:
                            continue

                        # Get webhook config
                        webhook_config = WebhookConfig.query.filter_by(server_id=server_id).first()

                        # Process each event
                        for event_data in events:
                            try:
                                # Process event (store in database)
                                player_event = processor.process_event(event_data)

                                if not player_event:
                                    continue

                                # Send Discord webhook if configured
                                if webhook_config:
                                    # Get player name
                                    player = Player.query.get(player_event.player_id)
                                    player_name = player.current_name if player else 'Unknown'

                                    # Get killer name if applicable
                                    killer_name = None
                                    if player_event.killer_id:
                                        killer = Player.query.get(player_event.killer_id)
                                        killer_name = killer.current_name if killer else player_event.killer_name

                                    # Send webhook
                                    DiscordWebhook.send_player_event(
                                        event=player_event,
                                        webhook_config=webhook_config,
                                        player_name=player_name,
                                        killer_name=killer_name
                                    )

                            except Exception as e:
                                logger.error(f"Error processing ADM event for server {server_id}: {e}", exc_info=True)

                    except Exception as e:
                        logger.error(f"Error monitoring ADM log for server {server_id}: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in ADM log monitor: {e}", exc_info=True)

    def add_server_monitor(self, server):
        """Add ADM monitor for a new server"""
        try:
            from adm_log_parser import ADMLogParser
            from event_processor import EventProcessor

            # Initialize ADM parser
            parser = ADMLogParser(server.profile_path)
            latest_log = parser.find_latest_adm_log()

            if latest_log:
                parser.tail_to_end()
                logger.info(f"Added ADM monitor for new server: {server.name}")

            # Initialize event processor
            processor = EventProcessor(server)

            self.adm_parsers[server.id] = parser
            self.event_processors[server.id] = processor

            return True

        except Exception as e:
            logger.error(f"Error adding ADM monitor for server {server.name}: {e}")
            return False

    def remove_server_monitor(self, server_id: int):
        """Remove ADM monitor for a deleted server"""
        if server_id in self.adm_parsers:
            del self.adm_parsers[server_id]
        if server_id in self.event_processors:
            del self.event_processors[server_id]
        logger.info(f"Removed ADM monitor for server ID: {server_id}")

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler and hasattr(self.scheduler, 'running') and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("ADM Monitor Scheduler shut down")
