"""
Discord Webhook Integration
Sends player events as embeds to Discord
"""
import requests
import logging
from typing import Dict, Optional
from player_event_models import WebhookConfig, PlayerEvent

logger = logging.getLogger(__name__)


class DiscordWebhook:
    """
    Discord Webhook sender for player events
    """

    # Discord colors
    COLORS = {
        'unconscious': 0xFFA500,  # Orange
        'regained_consciousness': 0x00FF00,  # Green
        'death': 0xFF0000,  # Red
        'kill': 0x8B0000,  # Dark Red
        'suicide': 0x800080,  # Purple
    }

    @staticmethod
    def send_webhook(webhook_url: str, embed: Dict) -> bool:
        """
        Send embed to Discord webhook

        Args:
            webhook_url: Discord webhook URL
            embed: Embed data

        Returns:
            bool: Success status
        """
        if not webhook_url:
            return False

        try:
            payload = {
                'embeds': [embed]
            }

            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 204:
                logger.debug(f"Discord webhook sent successfully")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Discord webhook: {e}")
            return False

    @staticmethod
    def create_unconscious_embed(player_name: str, position: Dict, timestamp: str) -> Dict:
        """
        Create embed for unconscious event

        Args:
            player_name: Player name
            position: Position dict {x, y, z}
            timestamp: ISO timestamp

        Returns:
            dict: Discord embed
        """
        return {
            'title': '😵 Player Unconscious',
            'description': f'**{player_name}** fell unconscious!',
            'color': DiscordWebhook.COLORS['unconscious'],
            'fields': [
                {
                    'name': '📍 Position',
                    'value': f'`{position["x"]:.1f}, {position["y"]:.1f}, {position["z"]:.1f}`',
                    'inline': True
                },
                {
                    'name': '⏰ Time',
                    'value': timestamp,
                    'inline': True
                }
            ],
            'footer': {
                'text': 'DayZ Server Events'
            },
            'timestamp': timestamp
        }

    @staticmethod
    def create_regained_consciousness_embed(player_name: str, position: Dict, timestamp: str) -> Dict:
        """
        Create embed for regained consciousness event

        Args:
            player_name: Player name
            position: Position dict {x, y, z}
            timestamp: ISO timestamp

        Returns:
            dict: Discord embed
        """
        return {
            'title': '💚 Player Regained Consciousness',
            'description': f'**{player_name}** woke up!',
            'color': DiscordWebhook.COLORS['regained_consciousness'],
            'fields': [
                {
                    'name': '📍 Position',
                    'value': f'`{position["x"]:.1f}, {position["y"]:.1f}, {position["z"]:.1f}`',
                    'inline': True
                },
                {
                    'name': '⏰ Time',
                    'value': timestamp,
                    'inline': True
                }
            ],
            'footer': {
                'text': 'DayZ Server Events'
            },
            'timestamp': timestamp
        }

    @staticmethod
    def create_suicide_embed(player_name: str, position: Dict, timestamp: str) -> Dict:
        """
        Create embed for suicide event

        Args:
            player_name: Player name
            position: Position dict {x, y, z}
            timestamp: ISO timestamp

        Returns:
            dict: Discord embed
        """
        return {
            'title': '💀 Player Suicide',
            'description': f'**{player_name}** committed suicide.',
            'color': DiscordWebhook.COLORS['suicide'],
            'fields': [
                {
                    'name': '📍 Position',
                    'value': f'`{position["x"]:.1f}, {position["y"]:.1f}, {position["z"]:.1f}`',
                    'inline': True
                },
                {
                    'name': '⏰ Time',
                    'value': timestamp,
                    'inline': True
                }
            ],
            'footer': {
                'text': 'DayZ Server Events'
            },
            'timestamp': timestamp
        }

    @staticmethod
    def create_death_embed(player_name: str, cause: str, position: Dict, timestamp: str,
                          killer_name: Optional[str] = None, weapon: Optional[str] = None,
                          distance: Optional[float] = None) -> Dict:
        """
        Create embed for death event

        Args:
            player_name: Victim name
            cause: Cause of death
            position: Position dict {x, y, z}
            timestamp: ISO timestamp
            killer_name: Killer name (optional)
            weapon: Weapon used (optional)
            distance: Kill distance (optional)

        Returns:
            dict: Discord embed
        """
        fields = []

        # Description based on death type
        if killer_name and weapon:
            if distance and distance > 0:
                description = f'**{player_name}** was killed by **{killer_name}**\nwith `{weapon}` from **{distance:.1f}m**'
            else:
                description = f'**{player_name}** was killed by **{killer_name}**\nwith `{weapon}`'
        elif cause:
            description = f'**{player_name}** died.\nCause: `{cause}`'
        else:
            description = f'**{player_name}** died.'

        # Position field
        fields.append({
            'name': '📍 Position',
            'value': f'`{position["x"]:.1f}, {position["y"]:.1f}, {position["z"]:.1f}`',
            'inline': True
        })

        # Time field
        fields.append({
            'name': '⏰ Time',
            'value': timestamp,
            'inline': True
        })

        # Weapon field (if PvP)
        if weapon and killer_name:
            fields.append({
                'name': '🔫 Weapon',
                'value': f'`{weapon}`',
                'inline': True
            })

        # Distance field (if ranged kill)
        if distance and distance > 0:
            fields.append({
                'name': '📏 Distance',
                'value': f'`{distance:.1f}m`',
                'inline': True
            })

        return {
            'title': '☠️ Player Death',
            'description': description,
            'color': DiscordWebhook.COLORS['death'],
            'fields': fields,
            'footer': {
                'text': 'DayZ Server Events'
            },
            'timestamp': timestamp
        }

    @staticmethod
    def create_kill_embed(killer_name: str, victim_name: str, weapon: str,
                         distance: float, position: Dict, timestamp: str) -> Dict:
        """
        Create embed for kill event

        Args:
            killer_name: Killer name
            victim_name: Victim name
            weapon: Weapon used
            distance: Kill distance
            position: Position dict {x, y, z}
            timestamp: ISO timestamp

        Returns:
            dict: Discord embed
        """
        if distance > 0:
            description = f'**{killer_name}** killed **{victim_name}**\nwith `{weapon}` from **{distance:.1f}m**'
        else:
            description = f'**{killer_name}** killed **{victim_name}**\nwith `{weapon}`'

        fields = [
            {
                'name': '📍 Position',
                'value': f'`{position["x"]:.1f}, {position["y"]:.1f}, {position["z"]:.1f}`',
                'inline': True
            },
            {
                'name': '⏰ Time',
                'value': timestamp,
                'inline': True
            },
            {
                'name': '🔫 Weapon',
                'value': f'`{weapon}`',
                'inline': True
            }
        ]

        if distance > 0:
            fields.append({
                'name': '📏 Distance',
                'value': f'`{distance:.1f}m`',
                'inline': True
            })

        return {
            'title': '🎯 Player Kill',
            'description': description,
            'color': DiscordWebhook.COLORS['kill'],
            'fields': fields,
            'footer': {
                'text': 'DayZ Server Events'
            },
            'timestamp': timestamp
        }

    @staticmethod
    def send_player_event(event: PlayerEvent, webhook_config: WebhookConfig,
                         player_name: str, killer_name: Optional[str] = None) -> bool:
        """
        Send player event to appropriate Discord webhook

        Args:
            event: PlayerEvent instance
            webhook_config: WebhookConfig instance
            player_name: Player name
            killer_name: Killer name (if applicable)

        Returns:
            bool: Success status
        """
        if not webhook_config:
            return False

        # Prepare position data
        position = {
            'x': event.position_x or 0,
            'y': event.position_y or 0,
            'z': event.position_z or 0
        }

        timestamp = event.timestamp.isoformat() if event.timestamp else ''

        # Determine webhook URL and embed based on event type
        webhook_url = None
        embed = None

        if event.event_type == 'unconscious':
            if webhook_config.unconscious_enabled and webhook_config.unconscious_webhook_url:
                webhook_url = webhook_config.unconscious_webhook_url
                embed = DiscordWebhook.create_unconscious_embed(player_name, position, timestamp)

        elif event.event_type == 'regained_consciousness':
            if webhook_config.unconscious_enabled and webhook_config.unconscious_webhook_url:
                webhook_url = webhook_config.unconscious_webhook_url
                embed = DiscordWebhook.create_regained_consciousness_embed(player_name, position, timestamp)

        elif event.event_type == 'suicide':
            if webhook_config.suicide_enabled and webhook_config.suicide_webhook_url:
                webhook_url = webhook_config.suicide_webhook_url
                embed = DiscordWebhook.create_suicide_embed(player_name, position, timestamp)

        elif event.event_type == 'death':
            if webhook_config.death_enabled and webhook_config.death_webhook_url:
                webhook_url = webhook_config.death_webhook_url
                embed = DiscordWebhook.create_death_embed(
                    player_name=player_name,
                    cause=event.cause_of_death or 'Unknown',
                    position=position,
                    timestamp=timestamp,
                    killer_name=killer_name or event.killer_name,
                    weapon=event.weapon,
                    distance=event.distance
                )

        elif event.event_type == 'kill':
            if webhook_config.death_enabled and webhook_config.death_webhook_url:
                webhook_url = webhook_config.death_webhook_url
                embed = DiscordWebhook.create_kill_embed(
                    killer_name=player_name,
                    victim_name=event.killer_name,  # In kill event, this is the victim
                    weapon=event.weapon or 'Unknown',
                    distance=event.distance or 0,
                    position=position,
                    timestamp=timestamp
                )

        # Send webhook if configured
        if webhook_url and embed:
            return DiscordWebhook.send_webhook(webhook_url, embed)

        return False
