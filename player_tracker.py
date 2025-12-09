from datetime import datetime, timedelta
from player_models import Player, PlayerSession, PlayerName, PlayerIP
from player_log_parser import PlayerLogParser
from database import db
import logging

logger = logging.getLogger(__name__)

class PlayerTracker:
    """
    High-performance player tracking system
    Handles player join/leave events and statistics
    """

    def __init__(self, server):
        self.server = server
        self.server_id = server.id

        # Initialize log parser with stdout log (contains player connection data)
        import os
        log_path = os.path.join(self.server.profile_path, 'logs', 'server_stdout.log')

        self.log_parser = PlayerLogParser(log_path)

    def get_or_create_player(self, guid: str, name: str, ip: str = None, port: int = None,
                             steam_id: str = None, bohemia_id: str = None) -> Player:
        """
        Get existing player or create new one
        Uses GUID as unique identifier
        """
        # Try to find existing player
        player = Player.query.filter_by(
            server_id=self.server_id,
            guid=guid
        ).first()

        if player:
            # Update existing player
            needs_update = False

            if name and name != player.current_name:
                player.current_name = name
                needs_update = True
                self._update_name_history(player, name)

            if ip and ip != player.current_ip:
                player.current_ip = ip
                needs_update = True
                self._update_ip_history(player, ip, port)

            if port and port != player.current_port:
                player.current_port = port
                needs_update = True

            if steam_id and not player.steam_id:
                player.steam_id = steam_id
                needs_update = True

            if bohemia_id and not player.bohemia_id:
                player.bohemia_id = bohemia_id
                needs_update = True

            if needs_update:
                player.updated_at = datetime.utcnow()
                db.session.commit()

            return player

        # Create new player
        player = Player(
            server_id=self.server_id,
            dayztools_id=Player.generate_dayztools_id(),
            guid=guid,
            steam_id=steam_id,
            bohemia_id=bohemia_id,
            current_name=name,
            current_ip=ip,
            current_port=port,
            is_online=False,
            total_playtime=0,
            session_count=0,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow()
        )

        db.session.add(player)
        db.session.commit()

        # Initialize name history
        if name:
            self._update_name_history(player, name)

        # Initialize IP history
        if ip:
            self._update_ip_history(player, ip, port)

        logger.info(f"Created new player: {name} ({guid}) - DayZTools ID: {player.dayztools_id}")

        return player

    def _update_name_history(self, player: Player, name: str):
        """Update player name history"""
        name_entry = PlayerName.query.filter_by(
            player_id=player.id,
            name=name
        ).first()

        if name_entry:
            # Update existing name entry
            name_entry.last_seen = datetime.utcnow()
            name_entry.usage_count += 1
        else:
            # Create new name entry
            name_entry = PlayerName(
                player_id=player.id,
                name=name,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                usage_count=1
            )
            db.session.add(name_entry)

        db.session.commit()

    def _update_ip_history(self, player: Player, ip: str, port: int = None):
        """Update player IP history"""
        ip_entry = PlayerIP.query.filter_by(
            player_id=player.id,
            ip_address=ip
        ).first()

        if ip_entry:
            # Update existing IP entry
            ip_entry.last_seen = datetime.utcnow()
            ip_entry.usage_count += 1
            if port:
                ip_entry.port = port
        else:
            # Create new IP entry
            ip_entry = PlayerIP(
                player_id=player.id,
                ip_address=ip,
                port=port,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                usage_count=1
            )
            db.session.add(ip_entry)

        db.session.commit()

    def handle_player_join(self, guid: str, name: str, ip: str = None, port: int = None,
                          steam_id: str = None, bohemia_id: str = None, timestamp: datetime = None):
        """
        Handle player join event
        Creates/updates player and starts new session
        """
        if not timestamp:
            timestamp = datetime.utcnow()

        # Get or create player
        player = self.get_or_create_player(guid, name, ip, port, steam_id, bohemia_id)

        # Check if player already has an open session (shouldn't happen, but handle it)
        open_session = PlayerSession.query.filter_by(
            player_id=player.id,
            leave_time=None
        ).first()

        if open_session:
            # Close the old session (probably a crash/disconnect that wasn't logged)
            self.handle_player_leave(player.id, timestamp=timestamp)

        # Create new session
        session = PlayerSession(
            player_id=player.id,
            join_time=timestamp,
            name_at_join=name,
            ip_at_join=ip,
            port_at_join=port
        )

        db.session.add(session)

        # Update player status
        player.is_online = True
        player.last_seen = timestamp
        player.session_count += 1

        db.session.commit()

        logger.info(f"Player joined: {name} ({guid}) at {timestamp}")

        return player, session

    def handle_player_leave(self, player_id: int = None, player_name: str = None, timestamp: datetime = None):
        """
        Handle player leave event
        Closes active session and updates statistics
        """
        if not timestamp:
            timestamp = datetime.utcnow()

        # Find player
        if player_id:
            player = Player.query.get(player_id)
        elif player_name:
            # Find by name (less reliable, but works for disconnects)
            player = Player.query.filter_by(
                server_id=self.server_id,
                current_name=player_name,
                is_online=True
            ).first()
        else:
            return None

        if not player:
            logger.warning(f"Could not find player for leave event: {player_name or player_id}")
            return None

        # Find open session
        session = PlayerSession.query.filter_by(
            player_id=player.id,
            leave_time=None
        ).first()

        if not session:
            logger.warning(f"No open session found for player: {player.current_name}")
            return None

        # Calculate session duration
        duration = int((timestamp - session.join_time).total_seconds())

        # Update session
        session.leave_time = timestamp
        session.duration = duration

        # Update player statistics
        player.is_online = False
        player.last_seen = timestamp
        player.total_playtime += duration

        db.session.commit()

        logger.info(f"Player left: {player.current_name} - Session duration: {duration}s")

        return player, session

    def process_log_events(self):
        """
        Process new log events
        Main entry point for log monitoring
        """
        # Read new log lines
        events = self.log_parser.read_new_lines()

        if not events:
            return

        # Merge events into complete player data
        join_events, leave_events = self.log_parser.merge_player_data(events)

        # Process join events
        for event in join_events:
            try:
                self.handle_player_join(
                    guid=event['guid'],
                    name=event['name'],
                    ip=event.get('ip'),
                    port=event.get('port'),
                    steam_id=event.get('steam_id'),
                    bohemia_id=event.get('bohemia_id'),
                    timestamp=event['timestamp']
                )
            except Exception as e:
                logger.error(f"Error processing join event: {e}")

        # Process leave events
        for event in leave_events:
            try:
                self.handle_player_leave(
                    player_name=event['name'],
                    timestamp=event['timestamp']
                )
            except Exception as e:
                logger.error(f"Error processing leave event: {e}")

    def sync_with_rcon(self):
        """
        Sync player tracking with RCon to detect currently online players
        This is called on initialization to ensure we track players that joined before the tracker started
        """
        try:
            from rcon_utils import RConManager

            logger.info(f"Syncing with RCon for server: {self.server.name}")
            success, players, message = RConManager.get_players(self.server)

            if not success:
                logger.warning(f"Could not sync with RCon: {message}")
                return 0

            if not players:
                logger.info("No players online to sync")
                return 0

            synced_count = 0
            timestamp = datetime.utcnow()

            for rcon_player in players:
                try:
                    guid = rcon_player.get('guid', 'N/A')
                    name = rcon_player.get('name', 'Unknown')

                    # Skip if no valid GUID
                    if guid == 'N/A' or not guid:
                        logger.warning(f"Skipping player {name} - no valid GUID")
                        continue

                    # Parse IP and port
                    ip_port = rcon_player.get('ip', '')
                    ip = None
                    port = None
                    if ':' in ip_port:
                        parts = ip_port.split(':')
                        ip = parts[0]
                        try:
                            port = int(parts[1])
                        except:
                            pass

                    # Get or create player
                    player = self.get_or_create_player(
                        guid=guid,
                        name=name,
                        ip=ip,
                        port=port
                    )

                    # Check if player already has an open session
                    open_session = PlayerSession.query.filter_by(
                        player_id=player.id,
                        leave_time=None
                    ).first()

                    if not open_session:
                        # Create new session for this currently online player
                        session = PlayerSession(
                            player_id=player.id,
                            join_time=timestamp,
                            name_at_join=name,
                            ip_at_join=ip,
                            port_at_join=port
                        )
                        db.session.add(session)

                        # Update player status
                        player.is_online = True
                        player.last_seen = timestamp
                        player.session_count += 1

                        synced_count += 1
                        logger.info(f"Synced online player: {name} ({guid})")
                    else:
                        logger.debug(f"Player {name} already has open session")

                except Exception as e:
                    logger.error(f"Error syncing player {rcon_player.get('name', 'Unknown')}: {e}")
                    continue

            if synced_count > 0:
                db.session.commit()
                logger.info(f"Successfully synced {synced_count} online player(s) from RCon")

            return synced_count

        except Exception as e:
            logger.error(f"Error during RCon sync: {e}", exc_info=True)
            return 0

    def update_online_players(self):
        """
        Update all currently online players
        Called by scheduler every 30 minutes
        """
        online_players = Player.query.filter_by(
            server_id=self.server_id,
            is_online=True
        ).all()

        timestamp = datetime.utcnow()

        for player in online_players:
            # Update last_seen
            player.last_seen = timestamp
            player.updated_at = timestamp

        if online_players:
            db.session.commit()
            logger.info(f"Updated {len(online_players)} online player(s)")

    def get_online_players(self):
        """Get list of currently online players"""
        return Player.query.filter_by(
            server_id=self.server_id,
            is_online=True
        ).all()

    def get_player_stats(self, player_id: int):
        """Get detailed statistics for a player"""
        player = Player.query.get(player_id)
        if not player:
            return None

        # Get all sessions
        sessions = PlayerSession.query.filter_by(
            player_id=player_id
        ).order_by(PlayerSession.join_time.desc()).all()

        # Get name history
        names = PlayerName.query.filter_by(
            player_id=player_id
        ).order_by(PlayerName.first_seen.desc()).all()

        # Get IP history
        ips = PlayerIP.query.filter_by(
            player_id=player_id
        ).order_by(PlayerIP.first_seen.desc()).all()

        return {
            'player': player,
            'sessions': sessions,
            'name_history': names,
            'ip_history': ips
        }

    def cleanup_old_sessions(self, days: int = 90):
        """
        Cleanup old sessions (optional maintenance task)
        Keep sessions from last N days
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        deleted = PlayerSession.query.filter(
            PlayerSession.join_time < cutoff_date
        ).delete()

        db.session.commit()

        logger.info(f"Cleaned up {deleted} old session(s)")
