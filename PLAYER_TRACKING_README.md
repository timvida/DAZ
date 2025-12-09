# DayZ Player Tracking System

## Übersicht

Das Player Tracking System ist ein hochperformantes, zuverlässiges System zur Verfolgung und Analyse von Spieler-Aktivitäten auf DayZ-Servern.

## Features

### 🎯 Kernfunktionen

1. **Echtzeit-Tracking**
   - Automatische Erkennung von Join/Leave-Events
   - Log-Monitoring alle 10 Sekunden
   - Sofortige Datenbank-Aktualisierung

2. **Eindeutige Identifikation**
   - **GUID** (BattlEye GUID) - Hauptidentifikator
   - **DayZTools-ID** - 16-Zeichen unique ID pro Spieler
   - **Steam-ID** - Automatisch extrahiert
   - **Bohemia-ID** - Automatisch extrahiert

3. **Umfangreiche Historie**
   - Namensänderungen mit Timestamps
   - IP-Adress-Verlauf
   - Komplette Session-Historie
   - Spielzeit-Tracking

4. **Performance-Optimiert**
   - Tail-Reading (nur neue Log-Zeilen)
   - Datenbank-Indizes
   - Batch-Updates alle 30 Minuten
   - Minimaler Ressourcen-Verbrauch

## Datenbank-Schema

### `players` - Haupt-Spieler-Tabelle
```sql
- id (INT, PRIMARY KEY)
- server_id (INT, FOREIGN KEY)
- dayztools_id (VARCHAR(16), UNIQUE) - Custom 16-Zeichen-ID
- guid (VARCHAR(64), INDEX) - BattlEye GUID
- steam_id (VARCHAR(20), INDEX) - Steam ID
- bohemia_id (VARCHAR(128)) - Bohemia Interactive ID
- current_name (VARCHAR(120)) - Aktueller Name
- current_ip (VARCHAR(45)) - Aktuelle IP
- current_port (INT) - Aktueller Port
- is_online (BOOLEAN) - Online-Status
- total_playtime (INT) - Gesamtspielzeit in Sekunden
- session_count (INT) - Anzahl Sessions
- first_seen (DATETIME) - Erstes Mal gesehen
- last_seen (DATETIME) - Letztes Mal gesehen
```

### `player_sessions` - Session-Tracking
```sql
- id (INT, PRIMARY KEY)
- player_id (INT, FOREIGN KEY, INDEX)
- join_time (DATETIME, INDEX) - Join-Zeitpunkt
- leave_time (DATETIME, NULLABLE) - Leave-Zeitpunkt (NULL = noch online)
- duration (INT) - Dauer in Sekunden
- name_at_join (VARCHAR(120)) - Name beim Join
- ip_at_join (VARCHAR(45)) - IP beim Join
- port_at_join (INT) - Port beim Join
```

### `player_names` - Namenshistorie
```sql
- id (INT, PRIMARY KEY)
- player_id (INT, FOREIGN KEY, INDEX)
- name (VARCHAR(120)) - Name
- first_seen (DATETIME) - Erstes Mal mit diesem Namen
- last_seen (DATETIME) - Letztes Mal mit diesem Namen
- usage_count (INT) - Wie oft dieser Name verwendet wurde
```

### `player_ips` - IP-Historie
```sql
- id (INT, PRIMARY KEY)
- player_id (INT, FOREIGN KEY, INDEX)
- ip_address (VARCHAR(45)) - IP-Adresse
- port (INT) - Port
- first_seen (DATETIME) - Erstes Mal mit dieser IP
- last_seen (DATETIME) - Letztes Mal mit dieser IP
- usage_count (INT) - Wie oft diese IP verwendet wurde
```

## Log-Parsing

### Erkannte Log-Pattern

1. **BattlEye Connection:**
   ```
   BattlEye Server: Player #1 BrandyMandy (93.217.26.147:54444) connected
   ```
   Extrahiert: Name, IP, Port

2. **BattlEye GUID:**
   ```
   BattlEye Server: Player #1 BrandyMandy - BE GUID: d2c1e1708ac2a40dea825a1fe7556a6b
   ```
   Extrahiert: Name, GUID

3. **Steam ID:**
   ```
   Player "BrandyMandy"(steamID=76561198081741282) is connected
   ```
   Extrahiert: Name, Steam-ID

4. **Bohemia ID:**
   ```
   Player BrandyMandy (id=96GpuDNvQHuVu5HGi-i2u5uPBUbW6wVeyBkZc6Gi298=) has connected.
   ```
   Extrahiert: Name, Bohemia-ID

5. **Disconnect:**
   ```
   Player BrandyMandy disconnected.
   ```
   Extrahiert: Name

## Scheduler-Konfiguration

### Log-Monitoring (Alle 10 Sekunden)
```python
trigger=IntervalTrigger(seconds=10)
```
- Liest neue Log-Zeilen
- Verarbeitet Join/Leave-Events
- Aktualisiert Datenbank sofort

### Online-Player-Update (Alle 30 Minuten)
```python
trigger=IntervalTrigger(minutes=30)
```
- Aktualisiert alle Online-Spieler
- Setzt `last_seen` Timestamp
- Verhindert Daten-Drift

## API-Endpoints

### 1. Players-Liste
```
GET /api/server/<server_id>/players
```

**Parameter:**
- `search` (optional) - Suchbegriff (Name, SteamID, GUID, DayZTools-ID)
- `online_only` (optional) - true/false - Nur Online-Spieler
- `limit` (optional) - Anzahl Ergebnisse (default: 100)
- `offset` (optional) - Pagination-Offset (default: 0)

**Response:**
```json
{
  "success": true,
  "total": 150,
  "limit": 100,
  "offset": 0,
  "players": [
    {
      "id": 1,
      "dayztools_id": "A1B2C3D4E5F6G7H8",
      "guid": "d2c1e1708ac2a40dea825a1fe7556a6b",
      "steam_id": "76561198081741282",
      "bohemia_id": "96GpuDNvQHuVu5HGi...",
      "current_name": "BrandyMandy",
      "current_ip": "93.217.26.147",
      "is_online": true,
      "total_playtime": 86400,
      "session_count": 42,
      "first_seen": "2025-01-01T10:00:00",
      "last_seen": "2025-12-09T12:00:00"
    }
  ]
}
```

### 2. Spieler-Profil
```
GET /api/server/<server_id>/player/<player_id>
```

**Response:**
```json
{
  "success": true,
  "player": { ... },
  "sessions": [
    {
      "id": 1,
      "join_time": "2025-12-09T10:00:00",
      "leave_time": "2025-12-09T12:00:00",
      "duration": 7200,
      "name_at_join": "BrandyMandy",
      "ip_at_join": "93.217.26.147",
      "port_at_join": 54444
    }
  ],
  "name_history": [
    {
      "name": "BrandyMandy",
      "first_seen": "2025-01-01T10:00:00",
      "last_seen": "2025-12-09T12:00:00",
      "usage_count": 42
    }
  ],
  "ip_history": [
    {
      "ip_address": "93.217.26.147",
      "port": 54444,
      "first_seen": "2025-01-01T10:00:00",
      "last_seen": "2025-12-09T12:00:00",
      "usage_count": 42
    }
  ]
}
```

## UI-Features

### Players-Liste (`/server/<id>/players`)
- **Echtzeit-Suche** - Instant-Filtering
- **Online-Filter** - Nur Online-Spieler anzeigen
- **Sortierung** - Online zuerst, dann nach Spielzeit
- **Pagination** - Load-More mit 50er-Schritten
- **Auto-Refresh** - Alle 30 Sekunden
- **Statistiken** - Total Players, Online Now, Total Playtime

### Spieler-Profil (`/server/<id>/player/<player_id>`)
- **Identities** - DayZTools-ID, GUID, Steam-ID, Bohemia-ID mit Copy-Buttons
- **Namenshistorie** - Alle verwendeten Namen
- **IP-Historie** - Alle verwendeten IP-Adressen
- **Session-Timeline** - Scrollbare Timeline aller Sessions
- **Statistiken** - Spielzeit, Sessions, First/Last Seen
- **Auto-Refresh** - Alle 60 Sekunden

## Initialization & Sync

### RCon-Synchronisation beim Start
Wenn der Player-Tracker initialisiert wird:
1. **Tail to End** - Log-Position wird ans Ende gesetzt (vermeidet Re-Reading großer Logs)
2. **RCon Sync** - Abfrage aktuell online Spieler via RCon
3. **Session-Erstellung** - Für alle online Spieler werden Sessions erstellt
4. **Log-Monitoring** - Ab jetzt werden neue Join/Leave-Events aus Logs getrackt

**Warum RCon-Sync?**
- Problem: Wenn Tracker startet, ist Log-Position am Ende
- Spieler die VOR dem Tracker-Start beigetreten sind, werden nicht erkannt
- Lösung: RCon "players" Befehl zeigt aktuell online Spieler
- Diese werden sofort in DB eingetragen mit aktiver Session

## Performance & Zuverlässigkeit

### Performance-Optimierungen

1. **Log-Reading**
   - Tail-Reading (nur neue Zeilen)
   - Position-Tracking im Log-File
   - Kein Re-Reading von alten Daten
   - RCon-Sync beim Start (statt komplettes Log parsen)

2. **Datenbank**
   - Indizes auf GUID, SteamID, Player-ID
   - Composite-Index auf (server_id, guid)
   - Optimierte Queries

3. **Caching**
   - Player-Tracker pro Server im Speicher
   - Keine redundanten DB-Queries
   - Batch-Updates

### Zuverlässigkeit

1. **Error-Handling**
   - Try-Catch um alle kritischen Operationen
   - Logging aller Fehler
   - Graceful Degradation

2. **Daten-Integrität**
   - Unique Constraints auf DayZTools-ID
   - Foreign Keys mit CASCADE
   - Transaction-Safety

3. **Session-Tracking**
   - Automatisches Schließen offener Sessions
   - Crash-Detection (Sessions ohne Leave)
   - Konsistenz-Checks

## Installation & Setup

### Automatisch (empfohlen)
Das System wird automatisch beim Web-Interface-Start initialisiert:
- Datenbank-Tabellen werden via `db.create_all()` erstellt
- Scheduler startet automatisch
- Tracker werden für alle installierten Server initialisiert

### Manuell
Wenn nötig, kann das System manuell initialisiert werden:
```python
from player_tracking_scheduler import PlayerTrackingScheduler

scheduler = PlayerTrackingScheduler(app, server_manager)
scheduler.start_tracking()
```

## Wartung

### Log-Cleanup
Optional: Alte Sessions können gelöscht werden:
```python
tracker.cleanup_old_sessions(days=90)  # Lösche Sessions älter als 90 Tage
```

### Datenbank-Optimierung
```sql
-- Re-index Tabellen
REINDEX TABLE players;
REINDEX TABLE player_sessions;

-- Vacuum (SQLite)
VACUUM;
```

## Monitoring

### Logs prüfen
```bash
tail -f webinterface.log
```

**Erwartete Log-Ausgaben:**
```
INFO:player_tracking_scheduler:Player Tracking Scheduler initialized
INFO:player_tracking_scheduler:Player tracker for 'DayZTools' will monitor: /home/dayzserver/.../server_stdout.log
INFO:player_tracker:Syncing with RCon for server: DayZTools
INFO:player_tracker:Synced online player: BrandyMandy (d2c1e1708ac2a40dea825a1fe7556a6b)
INFO:player_tracking_scheduler:Synced 1 currently online player(s) for 'DayZTools'
INFO:player_tracking_scheduler:Initialized player tracker for server: DayZTools
INFO:player_tracking_scheduler:Player event monitoring started (every 10 seconds)
INFO:player_tracking_scheduler:Online player update task started (every 30 minutes)
INFO:player_tracker:Created new player: BrandyMandy (d2c1e1708...) - DayZTools ID: A1B2C3D4E5F6G7H8
INFO:player_tracker:Player joined: BrandyMandy (d2c1e1708...) at 2025-12-09 12:00:00
INFO:player_tracker:Player left: BrandyMandy - Session duration: 7200s
INFO:player_tracking_scheduler:Updated 5 online player(s)
```

## Troubleshooting

### Problem: Spieler werden nicht getrackt
**Lösung:**
1. **RCon-Status prüfen**: Server muss laufen, RCon muss funktionieren
2. **Logs prüfen**: Schaue nach "Synced X currently online player(s)"
3. Log-Datei prüfen: `<server>/profiles/logs/server_stdout.log`
4. Permissions prüfen: Log-Datei muss lesbar sein
5. Scheduler-Status prüfen in Logs

**Wichtig**: Beim Tracker-Start werden ALLE aktuell online Spieler via RCon erkannt und in die Datenbank eingetragen. Wenn du bereits auf dem Server warst, solltest du sofort getrackt werden!

### Problem: Duplikate in Datenbank
**Lösung:**
- Sollte nicht passieren (Unique Constraint auf server_id + guid)
- Falls doch: Datenbank-Integrität prüfen

### Problem: Performance-Probleme
**Lösung:**
1. Alte Sessions cleanup: `tracker.cleanup_old_sessions(90)`
2. Datenbank-Indizes prüfen
3. Log-Intervall erhöhen (von 10s auf 30s)

## Sicherheit

- **Keine sensiblen Daten** - Nur öffentliche Identifiers
- **Read-Only Log-Access** - Nur Lesen, kein Schreiben
- **SQL-Injection-Safe** - SQLAlchemy ORM
- **XSS-Protected** - Jinja2 Auto-Escaping

## Lizenz

Teil des DayZ GameServer Web-Interface Projekts
