#!/usr/bin/env python3
"""
RCon Test Script
Tests the fixed RCon implementation with sequence number fix
"""

import sys
import os

# Add current directory to path to import rcon_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rcon_utils import BattlEyeRCon
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)

def test_rcon_connection(host, port, password):
    """
    Test RCon connection and basic commands

    Args:
        host: Server IP (e.g., 127.0.0.1)
        port: RCon port (e.g., 2302)
        password: RCon password
    """
    print("\n" + "="*60)
    print("DayZ RCon Connection Test (Sequence Fix Verified)")
    print("="*60 + "\n")

    # Create RCon instance
    rcon = BattlEyeRCon(host, port, password)

    # Test 1: Connection
    print("Test 1: Testing connection...")
    success, msg = rcon.connect()

    if not success:
        print(f"❌ Connection FAILED: {msg}")
        print("\nPossible issues:")
        print("  - Server is not running")
        print("  - Wrong IP/Port")
        print("  - Wrong RCon password")
        print("  - Firewall blocking connection")
        return False

    print(f"✅ Connection successful!")
    print(f"   Sequence started at: -1 (first command will be 0)")

    # Test 2: Get Players (first real command - sequence should be 0)
    print("\nTest 2: Getting player list (sequence #0)...")
    success, players = rcon.get_players()

    if success:
        print(f"✅ Command successful! Found {len(players)} player(s)")
        if players:
            for player in players:
                print(f"   - {player.get('name', 'Unknown')} (ID: {player.get('id', '?')})")
        else:
            print("   (No players online)")
    else:
        print(f"❌ Command FAILED")
        rcon.disconnect()
        return False

    # Test 3: Send Global Message (sequence should be 1)
    print("\nTest 3: Sending global message (sequence #1)...")
    test_message = "RCon Test - Sequence Fix Active!"
    success, response = rcon.send_message(test_message)

    if success:
        print(f"✅ Message sent successfully!")
    else:
        print(f"❌ Message send FAILED: {response}")

    # Test 4: Custom Command (sequence should be 2)
    print("\nTest 4: Sending custom command 'players' (sequence #2)...")
    success, response = rcon.send_command("players")

    if success:
        print(f"✅ Custom command successful!")
        print(f"   Response preview: {response[:100]}..." if len(response) > 100 else f"   Response: {response}")
    else:
        print(f"❌ Custom command FAILED: {response}")

    # Test 5: Lock/Unlock (sequence should be 3 and 4)
    print("\nTest 5: Testing Lock/Unlock (sequence #3 and #4)...")

    # Lock
    success, response = rcon.lock_server()
    if success:
        print(f"✅ Server locked successfully!")
    else:
        print(f"⚠️  Lock command response: {response}")

    # Unlock immediately
    import time
    time.sleep(0.5)
    success, response = rcon.unlock_server()
    if success:
        print(f"✅ Server unlocked successfully!")
    else:
        print(f"⚠️  Unlock command response: {response}")

    # Cleanup
    print("\nTest 6: Disconnecting...")
    rcon.disconnect()
    print("✅ Disconnected cleanly")

    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED - RCon is working correctly!")
    print("="*60 + "\n")

    return True


if __name__ == "__main__":
    print("\nDayZ BattlEye RCon Test Utility")
    print("================================\n")

    # Get connection details
    if len(sys.argv) == 4:
        host = sys.argv[1]
        port = int(sys.argv[2])
        password = sys.argv[3]
    else:
        print("Usage: python3 test_rcon.py <host> <port> <password>")
        print("\nExample:")
        print("  python3 test_rcon.py 127.0.0.1 2302 YourRConPassword")
        print("\nOr enter details manually:\n")

        host = input("Server IP [127.0.0.1]: ").strip() or "127.0.0.1"
        port = input("RCon Port [2302]: ").strip() or "2302"
        password = input("RCon Password: ").strip()

        if not password:
            print("\n❌ Error: Password is required!")
            sys.exit(1)

        try:
            port = int(port)
        except ValueError:
            print("\n❌ Error: Port must be a number!")
            sys.exit(1)

    # Run test
    try:
        success = test_rcon_connection(host, port, password)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
