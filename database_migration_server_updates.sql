-- ============================================
-- Database Migration: Add Server Auto-Update Fields
-- ============================================
-- This migration adds auto-update tracking fields to the game_servers table
--
-- WICHTIG: Diese Migration wird AUTOMATISCH beim Start des Web-Interfaces durchgeführt!
-- Du musst diese Datei NICHT manuell ausführen, es sei denn, die automatische Migration schlägt fehl.
--
-- Falls die automatische Migration fehlgeschlagen ist, kannst du diese Datei manuell ausführen:
-- sqlite3 gameserver.db < database_migration_server_updates.sql

-- Add update_available column (tracks if a server update is available)
ALTER TABLE game_servers
ADD COLUMN update_available BOOLEAN DEFAULT 0;

-- Add update_downloaded column (tracks if the update has been downloaded)
ALTER TABLE game_servers
ADD COLUMN update_downloaded BOOLEAN DEFAULT 0;

-- Add last_update_check column (tracks when we last checked for updates)
ALTER TABLE game_servers
ADD COLUMN last_update_check DATETIME;

-- Verify the changes
SELECT sql FROM sqlite_master WHERE type='table' AND name='game_servers';

-- ============================================
-- Notes:
-- ============================================
-- 1. This migration is safe to run on existing databases
-- 2. All new columns have default values, so existing servers will work fine
-- 3. The auto-update system will populate these fields automatically
-- 4. If you're doing a fresh install, these columns will be created automatically
--    and you don't need to run this migration
-- ============================================
