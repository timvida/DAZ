"""
Server Scheduler Manager
Handles scheduled tasks for game servers (restarts, messages, etc.)
"""

import json
import logging
import pytz
from datetime import datetime, timedelta
from threading import Thread
from database import db, ServerScheduler, GameServer
from rcon_utils import RConManager
from server_manager import ServerManager

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

logger = logging.getLogger(__name__)


class ServerSchedulerManager:
    """Manager for server scheduled tasks"""

    def __init__(self, app):
        """
        Initialize the scheduler manager

        Args:
            app: Flask application instance
        """
        self.app = app
        self.scheduler = None
        self.server_manager = ServerManager()
        self.timezone = pytz.timezone('Europe/Berlin')  # German timezone

        if APSCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler(timezone=self.timezone)
            self.scheduler.start()
            logger.info("Server Scheduler Manager initialized")
        else:
            logger.error("APScheduler not installed - Server scheduling is disabled")

    def load_all_schedulers(self):
        """Load all active schedulers from database and schedule them"""
        if not APSCHEDULER_AVAILABLE or not self.scheduler:
            logger.warning("Cannot load schedulers - APScheduler not available")
            return

        with self.app.app_context():
            try:
                # Get all active schedulers
                schedulers = ServerScheduler.query.filter_by(is_active=True).all()

                for sched in schedulers:
                    self._schedule_task(sched)

                logger.info(f"Loaded {len(schedulers)} active scheduler(s)")

            except Exception as e:
                logger.error(f"Error loading schedulers: {str(e)}")

    def _schedule_task(self, scheduler_obj):
        """
        Schedule a task using APScheduler

        Args:
            scheduler_obj: ServerScheduler database object
        """
        if not APSCHEDULER_AVAILABLE or not self.scheduler:
            return

        try:
            # Create job ID
            job_id = f'scheduler_{scheduler_obj.id}'

            # Remove existing job if it exists
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # Determine trigger type based on schedule_type
            schedule_type = scheduler_obj.schedule_type or 'cron'  # Default to cron for backwards compatibility

            if schedule_type == 'interval':
                # === INTERVAL SCHEDULER (Every X minutes) ===
                from apscheduler.triggers.interval import IntervalTrigger

                interval_minutes = scheduler_obj.interval_minutes or 60
                trigger = IntervalTrigger(
                    minutes=interval_minutes,
                    timezone=self.timezone
                )

                logger.info(f"Creating INTERVAL scheduler: {scheduler_obj.name} (every {interval_minutes} minutes)")

            else:
                # === CRON SCHEDULER (Fixed time) ===
                # Parse weekdays (comma-separated string to list of ints)
                weekdays = [int(d.strip()) for d in scheduler_obj.weekdays.split(',')]

                # Create cron trigger
                # In APScheduler: mon=0, tue=1, ..., sun=6
                trigger = CronTrigger(
                    hour=scheduler_obj.hour,
                    minute=scheduler_obj.minute,
                    day_of_week=','.join(str(d) for d in weekdays),
                    timezone=self.timezone
                )

                logger.info(f"Creating CRON scheduler: {scheduler_obj.name} (at {scheduler_obj.hour}:{scheduler_obj.minute:02d})")

            # Add new job
            self.scheduler.add_job(
                func=self._execute_scheduler_task,
                trigger=trigger,
                args=[scheduler_obj.id],
                id=job_id,
                name=f'{scheduler_obj.name} (Server ID: {scheduler_obj.server_id})',
                replace_existing=True
            )

            logger.info(f"✓ Scheduled task: {scheduler_obj.name} (ID: {scheduler_obj.id})")

        except Exception as e:
            logger.error(f"✗ Error scheduling task {scheduler_obj.id}: {str(e)}")

    def _execute_scheduler_task(self, scheduler_id):
        """
        Execute a scheduled task

        Args:
            scheduler_id: ID of the scheduler to execute
        """
        with self.app.app_context():
            try:
                scheduler_obj = ServerScheduler.query.get(scheduler_id)
                if not scheduler_obj or not scheduler_obj.is_active:
                    logger.warning(f"Scheduler {scheduler_id} not found or inactive")
                    return

                server = GameServer.query.get(scheduler_obj.server_id)
                if not server:
                    logger.error(f"Server {scheduler_obj.server_id} not found")
                    return

                logger.info(f"Executing scheduler: {scheduler_obj.name} (ID: {scheduler_id})")

                # Execute based on action type
                if scheduler_obj.action_type == 'restart':
                    self._execute_restart(scheduler_obj, server)
                elif scheduler_obj.action_type == 'message':
                    self._execute_message(scheduler_obj, server)
                else:
                    logger.error(f"Unknown action type: {scheduler_obj.action_type}")

                # Update last run time
                scheduler_obj.last_run = datetime.utcnow()
                db.session.commit()

            except Exception as e:
                logger.error(f"Error executing scheduler {scheduler_id}: {str(e)}")
                db.session.rollback()

    def _execute_restart(self, scheduler_obj, server):
        """
        Execute a server restart with warnings

        Args:
            scheduler_obj: ServerScheduler object
            server: GameServer object
        """
        try:
            # Check if server is running
            if server.status != 'running':
                logger.warning(f"Server {server.name} is not running, skipping restart")
                return

            # Parse warning minutes
            warning_minutes = []
            if scheduler_obj.warning_minutes:
                try:
                    warning_minutes = json.loads(scheduler_obj.warning_minutes)
                    warning_minutes.sort(reverse=True)  # Sort descending
                except:
                    warning_minutes = [60, 30, 15, 10, 5, 3, 2, 1]

            # Calculate total time until restart (max warning time)
            total_minutes = max(warning_minutes) if warning_minutes else 0

            # Start restart sequence in background thread
            Thread(
                target=self._restart_sequence,
                args=(server, warning_minutes, scheduler_obj.kick_all_players, scheduler_obj.kick_minutes_before)
            ).start()

            logger.info(f"Restart sequence initiated for server {server.name} in {total_minutes} minutes")

        except Exception as e:
            logger.error(f"Error in restart execution: {str(e)}")

    def _restart_sequence(self, server, warning_minutes, kick_players, kick_minutes):
        """
        Execute the complete restart sequence with warnings

        Args:
            server: GameServer object
            warning_minutes: List of warning times
            kick_players: Whether to kick players
            kick_minutes: Minutes before restart to kick
        """
        import time

        # IMPORTANT: Run in app context for DB and RCon operations
        with self.app.app_context():
            try:
                # Refresh server object from DB (we're in a new thread)
                server = GameServer.query.get(server.id)
                if not server:
                    logger.error("Server not found in restart sequence")
                    return

                # Sort warnings descending
                warnings_sorted = sorted(warning_minutes, reverse=True)

                # Send each warning at the appropriate time
                for i, minutes in enumerate(warnings_sorted):
                    # Calculate how long to wait before sending this warning
                    if i == 0:
                        # First warning - no wait needed
                        wait_time = 0
                    else:
                        # Wait the difference between previous and current warning
                        wait_time = (warnings_sorted[i-1] - minutes) * 60

                    if wait_time > 0:
                        logger.debug(f"Waiting {wait_time} seconds until next warning")
                        time.sleep(wait_time)

                    # Refresh server object to get current status
                    db.session.refresh(server)

                    # Check if server is still running
                    if server.status != 'running':
                        logger.warning(f"Server {server.name} is no longer running, aborting restart sequence")
                        return

                    # Send the warning via RCon
                    message = f"[Server] Restart in {minutes} minute{'s' if minutes != 1 else ''}!"
                    logger.info(f"Sending restart warning: {message}")

                    success, msg = RConManager.send_server_message(server, message)
                    if success:
                        logger.info(f"✓ Sent restart warning to {server.name}: {message}")
                    else:
                        logger.error(f"✗ Failed to send warning: {msg}")

                # Kick players if configured
                if kick_players and kick_minutes > 0:
                    # Wait until kick time
                    if warnings_sorted:
                        last_warning = warnings_sorted[-1]
                        if last_warning > kick_minutes:
                            wait_time = (last_warning - kick_minutes) * 60
                            logger.info(f"Waiting {wait_time} seconds until kick time")
                            time.sleep(wait_time)

                    logger.info(f"Kicking all players from {server.name} ({kick_minutes} min before restart)")

                    # Refresh server
                    db.session.refresh(server)

                    success, msg = RConManager.kick_all_players(server, reason="Server Restart")
                    if not success:
                        logger.error(f"✗ Failed to kick players: {msg}")
                    else:
                        logger.info(f"✓ Successfully kicked all players: {msg}")

                    # Wait remaining time until restart
                    if kick_minutes > 0:
                        logger.info(f"Waiting {kick_minutes} minute(s) until restart")
                        time.sleep(kick_minutes * 60)
                else:
                    # Wait remaining time from last warning to restart
                    if warnings_sorted:
                        wait_time = warnings_sorted[-1] * 60
                        logger.info(f"Waiting {wait_time} seconds until restart (no kick configured)")
                        time.sleep(wait_time)

                # Final check: is server still running?
                db.session.refresh(server)
                if server.status != 'running':
                    logger.warning(f"Server {server.name} is not running, skipping restart")
                    return

                # Restart the server
                logger.info(f"⟳ Executing server restart: {server.name}")
                success, message = self.server_manager.restart_server(server.id)

                if success:
                    logger.info(f"✓ Server {server.name} restarted successfully")
                else:
                    logger.error(f"✗ Failed to restart server {server.name}: {message}")

            except Exception as e:
                logger.error(f"✗ Error in restart sequence: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())


    def _execute_message(self, scheduler_obj, server):
        """
        Execute a scheduled message

        Args:
            scheduler_obj: ServerScheduler object
            server: GameServer object
        """
        try:
            if not scheduler_obj.custom_message:
                logger.warning(f"No message configured for scheduler {scheduler_obj.id}")
                return

            # Check if server is running
            if server.status != 'running':
                logger.warning(f"Server {server.name} is not running, skipping message")
                return

            # Send the message
            success, msg = RConManager.send_server_message(server, scheduler_obj.custom_message)

            if success:
                logger.info(f"Sent scheduled message to {server.name}: {scheduler_obj.custom_message}")
            else:
                logger.error(f"Failed to send message: {msg}")

        except Exception as e:
            logger.error(f"Error sending scheduled message: {str(e)}")

    def add_scheduler(self, server_id, name, action_type, schedule_type='cron', **kwargs):
        """
        Add a new scheduler

        Args:
            server_id: Server ID
            name: Scheduler name
            action_type: 'restart' or 'message'
            schedule_type: 'cron' (fixed time) or 'interval' (every X minutes)
            **kwargs: Additional schedule and action-specific parameters

        Returns:
            tuple: (success: bool, message: str, scheduler_id: int)
        """
        try:
            # Create scheduler
            scheduler_obj = ServerScheduler(
                server_id=server_id,
                name=name,
                action_type=action_type,
                schedule_type=schedule_type,
                is_active=kwargs.get('is_active', True)
            )

            # === Schedule Configuration ===
            if schedule_type == 'interval':
                # Interval scheduler: every X minutes
                interval_minutes = kwargs.get('interval_minutes', 60)
                if not isinstance(interval_minutes, int) or interval_minutes < 1:
                    return False, "Interval must be at least 1 minute", None

                scheduler_obj.interval_minutes = interval_minutes

            else:
                # Cron scheduler: fixed time
                hour = kwargs.get('hour')
                minute = kwargs.get('minute')
                weekdays = kwargs.get('weekdays', [])

                # Validate cron inputs
                if hour is None or not (0 <= hour <= 23):
                    return False, "Hour must be between 0 and 23", None

                if minute is None or not (0 <= minute <= 59):
                    return False, "Minute must be between 0 and 59", None

                if not weekdays or not all(0 <= d <= 6 for d in weekdays):
                    return False, "Invalid weekdays", None

                scheduler_obj.hour = hour
                scheduler_obj.minute = minute
                scheduler_obj.weekdays = ','.join(str(d) for d in sorted(weekdays))

            # === Action Configuration ===
            if action_type == 'restart':
                scheduler_obj.kick_all_players = kwargs.get('kick_all_players', True)
                scheduler_obj.kick_minutes_before = kwargs.get('kick_minutes_before', 1)
                warning_minutes = kwargs.get('warning_minutes', [60, 30, 15, 10, 5, 3, 2, 1])
                scheduler_obj.warning_minutes = json.dumps(warning_minutes)
            elif action_type == 'message':
                scheduler_obj.custom_message = kwargs.get('custom_message', '')

            db.session.add(scheduler_obj)
            db.session.commit()

            # Schedule the task
            if scheduler_obj.is_active:
                self._schedule_task(scheduler_obj)

            logger.info(f"✓ Created scheduler: {name} (ID: {scheduler_obj.id}, Type: {schedule_type})")
            return True, "Scheduler created successfully", scheduler_obj.id

        except Exception as e:
            db.session.rollback()
            logger.error(f"✗ Error creating scheduler: {str(e)}")
            return False, f"Error: {str(e)}", None

    def update_scheduler(self, scheduler_id, **kwargs):
        """
        Update an existing scheduler

        Args:
            scheduler_id: Scheduler ID
            **kwargs: Fields to update

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            scheduler_obj = ServerScheduler.query.get(scheduler_id)
            if not scheduler_obj:
                return False, "Scheduler not found"

            # Update fields
            for key, value in kwargs.items():
                if key == 'weekdays' and isinstance(value, list):
                    scheduler_obj.weekdays = ','.join(str(d) for d in sorted(value))
                elif key == 'warning_minutes' and isinstance(value, list):
                    scheduler_obj.warning_minutes = json.dumps(value)
                elif hasattr(scheduler_obj, key):
                    setattr(scheduler_obj, key, value)

            db.session.commit()

            # Reschedule if active
            if scheduler_obj.is_active:
                self._schedule_task(scheduler_obj)
            else:
                # Remove from scheduler if deactivated
                job_id = f'scheduler_{scheduler_id}'
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)

            logger.info(f"Updated scheduler {scheduler_id}")
            return True, "Scheduler updated successfully"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating scheduler: {str(e)}")
            return False, f"Error: {str(e)}"

    def delete_scheduler(self, scheduler_id):
        """
        Delete a scheduler

        Args:
            scheduler_id: Scheduler ID

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            scheduler_obj = ServerScheduler.query.get(scheduler_id)
            if not scheduler_obj:
                return False, "Scheduler not found"

            # Remove from APScheduler
            job_id = f'scheduler_{scheduler_id}'
            if self.scheduler and self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # Delete from database
            db.session.delete(scheduler_obj)
            db.session.commit()

            logger.info(f"Deleted scheduler {scheduler_id}")
            return True, "Scheduler deleted successfully"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting scheduler: {str(e)}")
            return False, f"Error: {str(e)}"

    def toggle_scheduler(self, scheduler_id, is_active):
        """
        Enable or disable a scheduler

        Args:
            scheduler_id: Scheduler ID
            is_active: True to enable, False to disable

        Returns:
            tuple: (success: bool, message: str)
        """
        return self.update_scheduler(scheduler_id, is_active=is_active)

    def get_server_schedulers(self, server_id):
        """
        Get all schedulers for a server

        Args:
            server_id: Server ID

        Returns:
            list: List of ServerScheduler objects
        """
        return ServerScheduler.query.filter_by(server_id=server_id).order_by(ServerScheduler.hour, ServerScheduler.minute).all()

    def get_scheduler(self, scheduler_id):
        """
        Get a scheduler by ID

        Args:
            scheduler_id: Scheduler ID

        Returns:
            ServerScheduler: Scheduler object or None
        """
        return ServerScheduler.query.get(scheduler_id)

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler and hasattr(self.scheduler, 'running') and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Server Scheduler Manager shut down")
