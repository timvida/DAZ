import re
import os
from datetime import datetime
from typing import Optional, Dict, Tuple

class PlayerLogParser:
    """
    Parses DayZ server console logs to extract player connection data
    Optimized for performance - only reads new log lines
    """

    # Regex patterns for log parsing
    PATTERNS = {
        # BattlEye Server: Player #1 BrandyMandy (93.217.26.147:54444) connected
        'be_connect': re.compile(
            r'BattlEye Server: Player #\d+ (?P<name>.+?) \((?P<ip>[\d\.]+):(?P<port>\d+)\) connected'
        ),

        # BattlEye Server: Player #1 BrandyMandy - BE GUID: d2c1e1708ac2a40dea825a1fe7556a6b
        'be_guid': re.compile(
            r'BattlEye Server: Player #\d+ (?P<name>.+?) - BE GUID: (?P<guid>[a-f0-9]{32})'
        ),

        # Player "BrandyMandy"(steamID=76561198081741282) is connected
        'steam_id': re.compile(
            r'Player "(?P<name>.+?)"\(steamID=(?P<steam_id>\d+)\) is connected'
        ),

        # Player BrandyMandy (id=96GpuDNvQHuVu5HGi-i2u5uPBUbW6wVeyBkZc6Gi298=) has connected.
        'bohemia_id': re.compile(
            r'Player (?P<name>.+?) \(id=(?P<bohemia_id>[A-Za-z0-9\+/=]+)\) has connected\.'
        ),

        # Player BrandyMandy disconnected.
        'disconnect': re.compile(
            r'Player (?P<name>.+?) disconnected\.'
        ),

        # Timestamp at start of line: 12:13:01
        'timestamp': re.compile(r'^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})'),
    }

    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        self.last_position = 0
        self.pending_players = {}  # Temporary storage for incomplete player data

    def parse_timestamp(self, line: str) -> Optional[datetime]:
        """Extract timestamp from log line"""
        match = self.PATTERNS['timestamp'].match(line)
        if match:
            now = datetime.now()
            hour = int(match.group('hour'))
            minute = int(match.group('minute'))
            second = int(match.group('second'))

            # Create datetime with today's date and parsed time
            return now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        return None

    def parse_line(self, line: str, timestamp: datetime) -> Optional[Dict]:
        """
        Parse a single log line and return player event data if found
        Returns dict with event type and data, or None
        """
        # Check for BattlEye connection (includes IP/Port)
        match = self.PATTERNS['be_connect'].search(line)
        if match:
            name = match.group('name')
            return {
                'event': 'be_connect',
                'timestamp': timestamp,
                'name': name,
                'ip': match.group('ip'),
                'port': int(match.group('port'))
            }

        # Check for BattlEye GUID
        match = self.PATTERNS['be_guid'].search(line)
        if match:
            return {
                'event': 'be_guid',
                'timestamp': timestamp,
                'name': match.group('name'),
                'guid': match.group('guid')
            }

        # Check for Steam ID
        match = self.PATTERNS['steam_id'].search(line)
        if match:
            return {
                'event': 'steam_id',
                'timestamp': timestamp,
                'name': match.group('name'),
                'steam_id': match.group('steam_id')
            }

        # Check for Bohemia ID
        match = self.PATTERNS['bohemia_id'].search(line)
        if match:
            return {
                'event': 'bohemia_id',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('bohemia_id')
            }

        # Check for disconnect
        match = self.PATTERNS['disconnect'].search(line)
        if match:
            return {
                'event': 'disconnect',
                'timestamp': timestamp,
                'name': match.group('name')
            }

        return None

    def read_new_lines(self):
        """
        Read only new lines from log file since last position
        Very performant - only reads what's new
        """
        if not os.path.exists(self.log_file_path):
            import logging
            logging.warning(f"Log file does not exist: {self.log_file_path}")
            return []

        events = []
        lines_read = 0

        try:
            with open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Seek to last position
                f.seek(self.last_position)

                # Read new lines
                for line in f:
                    lines_read += 1
                    line = line.strip()
                    if not line:
                        continue

                    # Parse timestamp
                    timestamp = self.parse_timestamp(line)
                    if not timestamp:
                        timestamp = datetime.now()

                    # Parse line for player events
                    event = self.parse_line(line, timestamp)
                    if event:
                        events.append(event)
                        import logging
                        logging.info(f"Found player event: {event['event']} - {event.get('name', 'Unknown')}")

                # Update position
                self.last_position = f.tell()

            # Debug logging
            if lines_read > 0:
                import logging
                logging.debug(f"Read {lines_read} new lines from log, found {len(events)} events")

        except Exception as e:
            import logging
            logging.error(f"Error reading log file {self.log_file_path}: {e}", exc_info=True)
            return []

        return events

    def merge_player_data(self, events: list) -> Tuple[list, list]:
        """
        Merge multiple events for the same player into complete player data
        Returns (join_events, leave_events)
        """
        join_events = []
        leave_events = []

        # Group events by player name
        player_data = {}

        for event in events:
            name = event.get('name')
            if not name:
                continue

            if name not in player_data:
                player_data[name] = {
                    'name': name,
                    'timestamp': event['timestamp']
                }

            # Merge data based on event type
            if event['event'] == 'be_connect':
                player_data[name]['ip'] = event['ip']
                player_data[name]['port'] = event['port']
                player_data[name]['join_timestamp'] = event['timestamp']

            elif event['event'] == 'be_guid':
                player_data[name]['guid'] = event['guid']

            elif event['event'] == 'steam_id':
                player_data[name]['steam_id'] = event['steam_id']

            elif event['event'] == 'bohemia_id':
                player_data[name]['bohemia_id'] = event['bohemia_id']

            elif event['event'] == 'disconnect':
                player_data[name]['leave_timestamp'] = event['timestamp']

        # Process merged data
        for name, data in player_data.items():
            # Join event - must have at least name and GUID
            if 'guid' in data and 'join_timestamp' in data:
                join_events.append({
                    'name': data['name'],
                    'guid': data['guid'],
                    'steam_id': data.get('steam_id'),
                    'bohemia_id': data.get('bohemia_id'),
                    'ip': data.get('ip'),
                    'port': data.get('port'),
                    'timestamp': data['join_timestamp']
                })

            # Leave event
            if 'leave_timestamp' in data:
                leave_events.append({
                    'name': data['name'],
                    'timestamp': data['leave_timestamp']
                })

        return join_events, leave_events

    def reset_position(self):
        """Reset log file position to beginning"""
        self.last_position = 0

    def tail_to_end(self):
        """Move position to end of file (skip existing logs)"""
        if os.path.exists(self.log_file_path):
            try:
                with open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(0, 2)  # Seek to end
                    self.last_position = f.tell()
            except Exception as e:
                print(f"Error tailing log file: {e}")
