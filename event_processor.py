"""
Event Processor - Processes ADM log events and stores them in database
"""
import json
import logging
from datetime import datetime
from typing import Dict, Optional
from database import db
from player_event_models import PlayerEvent, PlayerStats
from player_models import Player

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Processes player events from ADM logs
    Stores events in database and updates player statistics
    """

    def __init__(self, server):
        """
        Initialize EventProcessor for a server

        Args:
            server: GameServer instance
        """
        self.server = server
        self.server_id = server.id

    def find_player_by_bohemia_id(self, bohemia_id: str) -> Optional[Player]:
        """
        Find player by Bohemia ID

        Args:
            bohemia_id: Bohemia Interactive ID

        Returns:
            Player: Player instance or None
        """
        return Player.query.filter_by(
            server_id=self.server_id,
            bohemia_id=bohemia_id
        ).first()

    def get_or_create_player_stats(self, player_id: int) -> PlayerStats:
        """
        Get or create player stats

        Args:
            player_id: Player ID

        Returns:
            PlayerStats: PlayerStats instance
        """
        stats = PlayerStats.query.filter_by(player_id=player_id).first()

        if not stats:
            stats = PlayerStats(player_id=player_id)
            db.session.add(stats)
            db.session.commit()

        return stats

    def process_unconscious_event(self, event: Dict):
        """
        Process unconscious event

        Args:
            event: Event data from ADM parser
        """
        try:
            # Find player
            player = self.find_player_by_bohemia_id(event['bohemia_id'])
            if not player:
                logger.warning(f"Player not found for unconscious event: {event.get('name')} ({event['bohemia_id']})")
                return

            # Create event
            player_event = PlayerEvent(
                server_id=self.server_id,
                player_id=player.id,
                event_type='unconscious',
                timestamp=event['timestamp'],
                position_x=event['position']['x'],
                position_y=event['position']['y'],
                position_z=event['position']['z']
            )

            db.session.add(player_event)

            # Update player stats
            stats = self.get_or_create_player_stats(player.id)
            stats.unconscious_count += 1

            db.session.commit()

            logger.info(f"Processed unconscious event for {player.current_name}")
            return player_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing unconscious event: {e}", exc_info=True)

    def process_regained_consciousness_event(self, event: Dict):
        """
        Process regained consciousness event

        Args:
            event: Event data from ADM parser
        """
        try:
            # Find player
            player = self.find_player_by_bohemia_id(event['bohemia_id'])
            if not player:
                logger.warning(f"Player not found for regained consciousness event: {event.get('name')}")
                return

            # Create event
            player_event = PlayerEvent(
                server_id=self.server_id,
                player_id=player.id,
                event_type='regained_consciousness',
                timestamp=event['timestamp'],
                position_x=event['position']['x'],
                position_y=event['position']['y'],
                position_z=event['position']['z']
            )

            db.session.add(player_event)
            db.session.commit()

            logger.info(f"Processed regained consciousness event for {player.current_name}")
            return player_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing regained consciousness event: {e}", exc_info=True)

    def process_suicide_event(self, event: Dict):
        """
        Process suicide event

        Args:
            event: Event data from ADM parser
        """
        try:
            # Find player
            player = self.find_player_by_bohemia_id(event['bohemia_id'])
            if not player:
                logger.warning(f"Player not found for suicide event: {event.get('name')}")
                return

            # Create event
            player_event = PlayerEvent(
                server_id=self.server_id,
                player_id=player.id,
                event_type='suicide',
                timestamp=event['timestamp'],
                position_x=event['position']['x'],
                position_y=event['position']['y'],
                position_z=event['position']['z'],
                cause_of_death='Suicide'
            )

            db.session.add(player_event)

            # Update player stats
            stats = self.get_or_create_player_stats(player.id)
            stats.suicide_count += 1
            stats.total_deaths += 1

            db.session.commit()

            logger.info(f"Processed suicide event for {player.current_name}")
            return player_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing suicide event: {e}", exc_info=True)

    def process_death_event(self, event: Dict):
        """
        Process generic death event (not suicide, not PvP)

        Args:
            event: Event data from ADM parser
        """
        try:
            # Find player
            player = self.find_player_by_bohemia_id(event['bohemia_id'])
            if not player:
                logger.warning(f"Player not found for death event: {event.get('name')}")
                return

            # Determine cause of death
            cause = event.get('cause', 'Unknown')
            if event['event'] == 'bled_out':
                cause = 'Bled out'

            # Create event with stats
            details = None
            if 'stats' in event:
                details = json.dumps(event['stats'])

            player_event = PlayerEvent(
                server_id=self.server_id,
                player_id=player.id,
                event_type='death',
                timestamp=event['timestamp'],
                position_x=event['position']['x'],
                position_y=event['position']['y'],
                position_z=event['position']['z'],
                cause_of_death=cause,
                details=details
            )

            db.session.add(player_event)

            # Update player stats
            stats = self.get_or_create_player_stats(player.id)
            stats.total_deaths += 1

            db.session.commit()

            logger.info(f"Processed death event for {player.current_name} - Cause: {cause}")
            return player_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing death event: {e}", exc_info=True)

    def process_kill_event(self, event: Dict):
        """
        Process PvP kill event

        Args:
            event: Event data from ADM parser
        """
        try:
            # Find victim
            victim = self.find_player_by_bohemia_id(event['victim_bohemia_id'])
            if not victim:
                logger.warning(f"Victim not found for kill event: {event.get('victim_name')}")
                return

            # Find killer
            killer = self.find_player_by_bohemia_id(event['killer_bohemia_id'])
            killer_id = killer.id if killer else None

            # Create death event for victim
            victim_event = PlayerEvent(
                server_id=self.server_id,
                player_id=victim.id,
                event_type='death',
                timestamp=event['timestamp'],
                position_x=event['position']['x'],
                position_y=event['position']['y'],
                position_z=event['position']['z'],
                killer_id=killer_id,
                killer_name=event['killer_name'],
                weapon=event['weapon'],
                distance=event['distance'],
                cause_of_death='Killed by player'
            )

            db.session.add(victim_event)

            # Update victim stats
            victim_stats = self.get_or_create_player_stats(victim.id)
            victim_stats.total_deaths += 1

            # Create kill event for killer (if found)
            if killer:
                killer_event = PlayerEvent(
                    server_id=self.server_id,
                    player_id=killer.id,
                    event_type='kill',
                    timestamp=event['timestamp'],
                    position_x=event['position']['x'],
                    position_y=event['position']['y'],
                    position_z=event['position']['z'],
                    killer_name=event['victim_name'],  # In kill event, this is the victim
                    weapon=event['weapon'],
                    distance=event['distance']
                )

                db.session.add(killer_event)

                # Update killer stats
                killer_stats = self.get_or_create_player_stats(killer.id)
                killer_stats.total_kills += 1

                # Update longest kill
                if event['distance'] > killer_stats.longest_kill_distance:
                    killer_stats.longest_kill_distance = event['distance']
                    killer_stats.longest_kill_weapon = event['weapon']

            db.session.commit()

            logger.info(f"Processed kill event: {event['killer_name']} killed {event['victim_name']} with {event['weapon']} from {event['distance']}m")
            return victim_event

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing kill event: {e}", exc_info=True)

    def process_event(self, event: Dict):
        """
        Process any event type

        Args:
            event: Event data from ADM parser

        Returns:
            PlayerEvent: Created event or None
        """
        event_type = event.get('event')

        if event_type == 'unconscious':
            return self.process_unconscious_event(event)

        elif event_type == 'regained_consciousness':
            return self.process_regained_consciousness_event(event)

        elif event_type == 'suicide':
            return self.process_suicide_event(event)

        elif event_type == 'killed_by_player':
            return self.process_kill_event(event)

        elif event_type in ['died', 'bled_out']:
            return self.process_death_event(event)

        else:
            logger.warning(f"Unknown event type: {event_type}")
            return None

    def process_events(self, events: list) -> list:
        """
        Process multiple events

        Args:
            events: List of events from ADM parser

        Returns:
            list: List of created PlayerEvent instances
        """
        created_events = []

        for event in events:
            try:
                player_event = self.process_event(event)
                if player_event:
                    created_events.append(player_event)
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
                continue

        return created_events
