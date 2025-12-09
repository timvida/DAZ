"""
DayZ ADM Log Parser
Parses Administration Log files for player events (deaths, unconscious, suicides)
"""
import re
import os
import glob
from datetime import datetime
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class ADMLogParser:
    """
    Parses DayZ server ADM logs to extract player events
    Optimized for performance - only reads new log lines
    """

    # Regex patterns for log parsing
    # Format: HH:MM:SS | Player "Name" (DEAD) (id=... pos=<x, y, z>) ...
    # IMPORTANT: Bohemia IDs can contain: A-Z, a-z, 0-9, +, /, -, =
    PATTERNS = {
        # PvP Kill: Player "Brandy" (DEAD) (id=... pos=<...>) killed by Player "Scotty" (id=... pos=<...>) with M4-A1 from 10.3476 meters
        'killed_by_player': re.compile(
            r'Player "(?P<victim_name>.+?)" \(DEAD\) \(id=(?P<victim_id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) killed by Player "(?P<killer_name>.+?)" \(id=(?P<killer_id>[A-Za-z0-9\+/\-=]+) pos=<[\d\.,\s]+>\) with (?P<weapon>.+?) from (?P<distance>[\d\.]+) meters'
        ),

        # Killed by NPC: Player "Survivor" (DEAD) (id=... pos=<...>) killed by Infected
        # IMPORTANT: Use negative lookahead to NOT match "killed by Player" (PvP kills)
        'killed_by_npc': re.compile(
            r'Player "(?P<name>.+?)" \(DEAD\) \(id=(?P<id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) killed by (?!Player)(?P<killer>.+?)$'
        ),

        # Suicide: Player "Brandy" (id=... pos=<...>) performed EmoteSuicide with HuntingKnife
        'suicide': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) performed EmoteSuicide(?: with (?P<weapon>.+?))?'
        ),

        # Player unconscious
        'unconscious': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\)(?:\[HP: [\d\.]+\])? (?:hit by .+?)? is unconscious'
        ),

        # Player regained consciousness
        'regained_consciousness': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) regained consciousness'
        ),

        # Player bled out
        'bled_out': re.compile(
            r'Player "(?P<name>.+?)" \(DEAD\) \(id=(?P<id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) bled out'
        ),

        # Player died with stats
        'died_stats': re.compile(
            r'Player "(?P<name>.+?)" \(DEAD\) \(id=(?P<id>[A-Za-z0-9\+/\-=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) died\. Stats>'
        ),

        # Timestamp: HH:MM:SS |
        'timestamp': re.compile(r'^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) \| '),
    }

    def __init__(self, profiles_path: str):
        """
        Initialize ADM log parser

        Args:
            profiles_path: Path to server profiles folder
        """
        self.profiles_path = profiles_path
        self.log_file_path = None
        self.last_position = 0

    def find_latest_adm_log(self) -> Optional[str]:
        """
        Find the most recent DayZServer_*.ADM file

        Returns:
            str: Path to latest ADM file, or None if not found
        """
        try:
            # Look for DayZServer_*.ADM files
            pattern = os.path.join(self.profiles_path, 'DayZServer_*.ADM')
            adm_files = glob.glob(pattern)

            if not adm_files:
                logger.warning(f"No ADM files found in: {self.profiles_path}")
                return None

            # Sort by modification time (most recent first)
            adm_files.sort(key=os.path.getmtime, reverse=True)
            latest = adm_files[0]

            logger.debug(f"Found latest ADM log: {os.path.basename(latest)}")
            return latest

        except Exception as e:
            logger.error(f"Error finding ADM log: {e}")
            return None

    def update_log_file(self):
        """
        Update to the latest ADM log file
        Handles server restarts that create new log files
        """
        latest = self.find_latest_adm_log()

        if latest and latest != self.log_file_path:
            logger.info(f"Switching to new ADM log: {os.path.basename(latest)}")
            self.log_file_path = latest
            # Reset position when switching files
            self.last_position = 0
            # Tail to end to skip existing content
            self.tail_to_end()

    def parse_timestamp(self, line: str) -> Optional[datetime]:
        """Extract timestamp from log line"""
        match = self.PATTERNS['timestamp'].match(line)
        if match:
            now = datetime.now()
            hour = int(match.group('hour'))
            minute = int(match.group('minute'))
            second = int(match.group('second'))

            return now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        return None

    def parse_line(self, line: str, timestamp: datetime) -> Optional[Dict]:
        """
        Parse a single log line and return event data if found

        Args:
            line: Log line to parse
            timestamp: Timestamp of the log entry

        Returns:
            dict: Event data, or None if no event found
        """
        # CRITICAL: Ignore HIT messages (damage messages, not deaths)
        # HIT messages contain "[HP: X] hit by" and are NOT death events
        if '[HP:' in line and 'hit by' in line:
            logger.debug(f"Skipping HIT message (not a death): {line[:100]}")
            return None

        # Check patterns in order of specificity (most specific first)

        # 1. Check for suicide
        match = self.PATTERNS['suicide'].search(line)
        if match:
            weapon = match.group('weapon') if match.group('weapon') else 'Unknown'
            logger.debug(f"✓ Matched SUICIDE pattern: {match.group('name')} with {weapon}")
            return {
                'event': 'suicide',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'weapon': weapon,
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        # 2. Check for PvP kill
        match = self.PATTERNS['killed_by_player'].search(line)
        if match:
            logger.debug(f"✓ Matched PvP KILL pattern: {match.group('killer_name')} killed {match.group('victim_name')} with {match.group('weapon')} from {match.group('distance')}m")
            return {
                'event': 'killed_by_player',
                'timestamp': timestamp,
                'victim_name': match.group('victim_name'),
                'victim_bohemia_id': match.group('victim_id'),
                'killer_name': match.group('killer_name'),
                'killer_bohemia_id': match.group('killer_id'),
                'weapon': match.group('weapon'),
                'distance': float(match.group('distance')),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        # 3. Check for NPC kill (Infected, Wolf, Bear, etc)
        match = self.PATTERNS['killed_by_npc'].search(line)
        if match:
            logger.debug(f"✓ Matched NPC KILL pattern: {match.group('name')} killed by {match.group('killer')}")
            return {
                'event': 'died',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                },
                'cause': match.group('killer')  # "Infected", "Wolf", etc
            }

        # 4. Check for bled out
        match = self.PATTERNS['bled_out'].search(line)
        if match:
            return {
                'event': 'bled_out',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        # 5. Check for death with stats
        match = self.PATTERNS['died_stats'].search(line)
        if match:
            return {
                'event': 'died',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                },
                'cause': 'Unknown'
            }

        # 6. Check for unconscious
        match = self.PATTERNS['unconscious'].search(line)
        if match:
            return {
                'event': 'unconscious',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        # 7. Check for regained consciousness
        match = self.PATTERNS['regained_consciousness'].search(line)
        if match:
            return {
                'event': 'regained_consciousness',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        return None

    def read_new_lines(self) -> List[Dict]:
        """
        Read only new lines from log file since last position

        Returns:
            list: List of parsed events
        """
        # Update to latest log file (handles server restarts)
        self.update_log_file()

        if not self.log_file_path or not os.path.exists(self.log_file_path):
            logger.warning(f"No ADM log file found at: {self.log_file_path}")
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

                    # Debug: Log the raw line
                    logger.debug(f"ADM Line {lines_read}: {line[:200]}")  # First 200 chars

                    # Parse timestamp and remove it from line
                    timestamp_match = self.PATTERNS['timestamp'].match(line)
                    if timestamp_match:
                        # Extract timestamp
                        now = datetime.now()
                        hour = int(timestamp_match.group('hour'))
                        minute = int(timestamp_match.group('minute'))
                        second = int(timestamp_match.group('second'))
                        timestamp = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

                        # Remove timestamp from line (keep only the content after "HH:MM:SS | ")
                        line = line[timestamp_match.end():]
                        logger.debug(f"Stripped timestamp, line now: {line[:100]}")
                    else:
                        timestamp = datetime.now()
                        logger.debug(f"No timestamp found in line, using current time")

                    # Parse line for events
                    event = self.parse_line(line, timestamp)
                    if event:
                        events.append(event)
                        logger.info(f"✓ Found ADM event: {event['event']} - {event.get('name', 'Unknown')}")
                    else:
                        # Debug: Log why line wasn't matched
                        if any(keyword in line.lower() for keyword in ['unconscious', 'dead', 'killed', 'suicide', 'died', 'bled']):
                            logger.warning(f"Line contains event keyword but wasn't matched: {line[:300]}")

                # Update position
                self.last_position = f.tell()

            if lines_read > 0:
                logger.info(f"Read {lines_read} new lines from ADM log, found {len(events)} events")
                if lines_read > 0 and len(events) == 0:
                    logger.warning(f"Lines were read but NO events were found. Check regex patterns!")
            else:
                logger.debug(f"No new lines in ADM log (position: {self.last_position})")

        except Exception as e:
            logger.error(f"Error reading ADM log {self.log_file_path}: {e}", exc_info=True)
            return []

        return events

    def tail_to_end(self):
        """Move position to end of file (skip existing logs)"""
        if self.log_file_path and os.path.exists(self.log_file_path):
            try:
                with open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(0, 2)  # Seek to end
                    self.last_position = f.tell()
                logger.debug(f"Tailed to end of ADM log: {os.path.basename(self.log_file_path)}")
            except Exception as e:
                logger.error(f"Error tailing ADM log: {e}")

    def reset_position(self):
        """Reset log file position to beginning"""
        self.last_position = 0
