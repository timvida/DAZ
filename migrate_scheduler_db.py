#!/usr/bin/env python3
"""
Database Migration Script for Scheduler Updates
Adds new fields for interval-based scheduling
"""

import sqlite3
import os
import sys

def migrate_database():
    """Add new columns to server_schedulers table"""

    db_path = os.path.join(os.path.dirname(__file__), 'gameserver.db')

    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        return False

    print("🔧 Starting database migration...")
    print(f"   Database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(server_schedulers)")
        columns = [row[1] for row in cursor.fetchall()]

        print(f"\n📋 Existing columns: {', '.join(columns)}")

        changes_made = False

        # Add schedule_type column if it doesn't exist
        if 'schedule_type' not in columns:
            print("\n➕ Adding 'schedule_type' column...")
            cursor.execute("""
                ALTER TABLE server_schedulers
                ADD COLUMN schedule_type VARCHAR(20) DEFAULT 'cron'
            """)
            changes_made = True
            print("   ✓ Added 'schedule_type' column")
        else:
            print("\n✓ 'schedule_type' column already exists")

        # Add interval_minutes column if it doesn't exist
        if 'interval_minutes' not in columns:
            print("\n➕ Adding 'interval_minutes' column...")
            cursor.execute("""
                ALTER TABLE server_schedulers
                ADD COLUMN interval_minutes INTEGER
            """)
            changes_made = True
            print("   ✓ Added 'interval_minutes' column")
        else:
            print("\n✓ 'interval_minutes' column already exists")

        # Update existing schedulers to have schedule_type = 'cron' if NULL
        if changes_made:
            print("\n🔄 Updating existing schedulers...")
            cursor.execute("""
                UPDATE server_schedulers
                SET schedule_type = 'cron'
                WHERE schedule_type IS NULL
            """)
            updated = cursor.rowcount
            print(f"   ✓ Updated {updated} existing scheduler(s)")

        conn.commit()
        conn.close()

        if changes_made:
            print("\n✅ Migration completed successfully!")
            print("\n📝 Changes:")
            print("   • Added 'schedule_type' field (cron/interval)")
            print("   • Added 'interval_minutes' field")
            print("   • Existing schedulers set to 'cron' type")
        else:
            print("\n✅ Database is already up to date!")

        return True

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("  Scheduler Database Migration")
    print("=" * 60)
    print()

    success = migrate_database()

    print("\n" + "=" * 60)
    if success:
        print("✅ Migration completed! You can now restart the web interface.")
        print("\nNew features:")
        print("  • Interval-based message scheduling (every X minutes)")
        print("  • Improved scheduler workflow")
        sys.exit(0)
    else:
        print("❌ Migration failed! Please check the errors above.")
        sys.exit(1)
