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
    PATTERNS = {
        # Player "Hexchen" (id=2Hnkevo6Z3K3205vN-R-6Q9xPqea7nPPWxbePK8l9pU= pos=<13373.9, 5370.2, 5.9>) is unconscious
        'unconscious': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\)\[HP: (?P<hp>[\d\.]+)\] (?:hit by .+ for [\d\.]+ damage \(.+\)\s+)?.*?is unconscious'
        ),

        # Simpler pattern for unconscious without HP
        'unconscious_simple': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) is unconscious'
        ),

        # Player "Hexchen" (id=2Hnkevo6Z3K3205vN-R-6Q9xPqea7nPPWxbePK8l9pU= pos=<13375.9, 5370.1, 5.9>) regained consciousness
        'regained_consciousness': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) regained consciousness'
        ),

        # Player "Brandy" (DEAD) (id=hQbMz6ZxsMudsUhepezzVlXWJl1KJ991DebofUxQ1ac= pos=<6012.7, 1930.9, 6.2>) killed by Player "BrandyMandy" (id=96GpuDNvQHuVu5HGi-i2u5uPBUbW6wVeyBkZc6Gi298= pos=<5977.8, 2002.7, 3.4>) with M4-A1 from 79.9567 meters
        'killed_by_player': re.compile(
            r'Player "(?P<victim_name>.+?)" \(DEAD\) \(id=(?P<victim_id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\).+? killed by Player "(?P<killer_name>.+?)" \(id=(?P<killer_id>[A-Za-z0-9\+/=]+).+?\) with (?P<weapon>.+?) from (?P<distance>[\d\.]+) meters'
        ),

        # Player "Brandy" (DEAD) (id=... pos=<...>) killed by Player "X" with (MeleeFist)
        'killed_by_player_melee': re.compile(
            r'Player "(?P<victim_name>.+?)" \(DEAD\) \(id=(?P<victim_id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\).+? killed by Player "(?P<killer_name>.+?)" \(id=(?P<killer_id>[A-Za-z0-9\+/=]+).+?\) with \((?P<weapon>Melee[A-Za-z]+)\)'
        ),

        # Player "Hexchen" (DEAD) (id=... pos=<...>) died. Stats> Water: 914.234 Energy: 789.689 Bleed sources: 0
        'died_stats': re.compile(
            r'Player "(?P<name>.+?)" \(DEAD\) \(id=(?P<id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) died\. Stats> Water: (?P<water>[\d\.]+) Energy: (?P<energy>[\d\.]+) Bleed sources: (?P<bleed>[\d]+)'
        ),

        # Player "Brandy" (DEAD) (id=... pos=<...>) bled out
        'bled_out': re.compile(
            r'Player "(?P<name>.+?)" \(DEAD\) \(id=(?P<id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) bled out'
        ),

        # Player "BrandyMandy" (id=... pos=<...>) committed suicide
        'suicide': re.compile(
            r'Player "(?P<name>.+?)" \(id=(?P<id>[A-Za-z0-9\+/=]+) pos=<(?P<x>[\d\.]+), (?P<y>[\d\.]+), (?P<z>[\d\.]+)>\) committed suicide'
        ),

        # Timestamp: 14:20:11 | ...
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
        # Check for suicide (check first as it's most specific)
        match = self.PATTERNS['suicide'].search(line)
        if match:
            return {
                'event': 'suicide',
                'timestamp': timestamp,
                'name': match.group('name'),
                'bohemia_id': match.group('id'),
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        # Check for PvP kill (with distance)
        match = self.PATTERNS['killed_by_player'].search(line)
        if match:
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

        # Check for PvP kill (melee, no distance)
        match = self.PATTERNS['killed_by_player_melee'].search(line)
        if match:
            return {
                'event': 'killed_by_player',
                'timestamp': timestamp,
                'victim_name': match.group('victim_name'),
                'victim_bohemia_id': match.group('victim_id'),
                'killer_name': match.group('killer_name'),
                'killer_bohemia_id': match.group('killer_id'),
                'weapon': match.group('weapon'),
                'distance': 0.0,  # Melee = close range
                'position': {
                    'x': float(match.group('x')),
                    'y': float(match.group('y')),
                    'z': float(match.group('z'))
                }
            }

        # Check for bled out
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

        # Check for death with stats
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
                'stats': {
                    'water': float(match.group('water')),
                    'energy': float(match.group('energy')),
                    'bleed_sources': int(match.group('bleed'))
                }
            }

        # Check for unconscious
        match = self.PATTERNS['unconscious_simple'].search(line)
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

        # Check for regained consciousness
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

                    # Parse timestamp
                    timestamp = self.parse_timestamp(line)
                    if not timestamp:
                        timestamp = datetime.now()

                    # Parse line for events
                    event = self.parse_line(line, timestamp)
                    if event:
                        events.append(event)
                        logger.info(f"Found ADM event: {event['event']} - {event.get('name', 'Unknown')}")

                # Update position
                self.last_position = f.tell()

            if lines_read > 0:
                logger.info(f"Read {lines_read} new lines from ADM log, found {len(events)} events")
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
