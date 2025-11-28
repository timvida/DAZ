from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModUpdateScheduler:
    """Background scheduler for automatic mod updates"""

    def __init__(self, app, mod_manager):
        self.app = app
        self.mod_manager = mod_manager
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("Mod Update Scheduler initialized")

    def start_auto_update_task(self):
        """Start the auto-update task (runs every 60 minutes)"""
        self.scheduler.add_job(
            func=self._update_mods_task,
            trigger=IntervalTrigger(minutes=60),
            id='mod_auto_update',
            name='Auto-update mods from Steam Workshop',
            replace_existing=True
        )
        logger.info("Auto-update task scheduled (every 60 minutes)")

    def _update_mods_task(self):
        """Background task to update all mods with auto_update enabled"""
        with self.app.app_context():
            try:
                logger.info("Starting mod auto-update task...")
                success, message, count = self.mod_manager.update_all_mods()

                if success:
                    logger.info(f"Mod auto-update completed: {message}")
                else:
                    logger.error(f"Mod auto-update failed: {message}")

            except Exception as e:
                logger.error(f"Error in mod auto-update task: {str(e)}")

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Mod Update Scheduler shut down")
