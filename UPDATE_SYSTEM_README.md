# DayZ Server Auto-Update System

## Übersicht

Das Auto-Update-System prüft automatisch alle 4 Stunden, ob neue DayZ Server Updates verfügbar sind. Wenn ein Update gefunden wird, wird es automatisch heruntergeladen und im Dashboard angezeigt.

## Features

### 1. Automatische Update-Prüfung
- **Intervall**: Alle 4 Stunden (240 Minuten)
- **Methode**: SteamCMD `app_update` mit `validate` Flag
- **Automatischer Download**: Ja, Updates werden automatisch heruntergeladen
- **Hintergrund-Prozess**: Läuft über APScheduler im Hintergrund

### 2. Dashboard-Benachrichtigung
- **Update-Banner**: Wird oben im Server-Dashboard angezeigt
- **Farbe**: Gelb/Orange für hohe Sichtbarkeit
- **Aktion**: "Jetzt neu starten" Button zum sofortigen Anwenden des Updates
- **Automatisches Ausblenden**: Banner verschwindet nach Server-Neustart

### 3. Manuelle Update-Prüfung
- **Button**: "Nach Updates suchen" im Server-Dashboard
- **Sofortige Prüfung**: Prüft sofort bei SteamCMD, ohne auf den Scheduler zu warten
- **Feedback**: Zeigt Erfolgsmeldung oder Status an

### 4. Update-Anwendung
- **Methode**: Server-Neustart
- **Datenverlust**: Nein, alle Daten bleiben erhalten
- **Spieler**: Werden beim Neustart getrennt (Standard DayZ-Verhalten)
- **Automatisches Zurücksetzen**: Update-Flags werden nach erfolgreichem Neustart zurückgesetzt

## Datenbank-Schema

### Neue Felder in `game_servers` Tabelle:

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `update_available` | BOOLEAN | Ob ein Server-Update verfügbar ist |
| `update_downloaded` | BOOLEAN | Ob das Update bereits heruntergeladen wurde |
| `last_update_check` | DATETIME | Zeitstempel der letzten Prüfung |

## API Endpoints

### 1. Manuelle Update-Prüfung
```
POST /api/server/<server_id>/update/check
```
**Antwort:**
```json
{
  "success": true,
  "message": "Update was available and has been downloaded",
  "update_available": true
}
```

### 2. Update-Status abrufen
```
GET /api/server/<server_id>/update/status
```
**Antwort:**
```json
{
  "update_available": true,
  "update_downloaded": true,
  "last_update_check": "2025-12-09T10:30:00"
}
```

## Installation

### Für bestehende Installationen:

1. **Datenbank migrieren** (für bestehende Installationen):
   ```bash
   cd /pfad/zu/gameserver-webinterface
   sqlite3 gameserver.db < database_migration_server_updates.sql
   ```

2. **Web-Interface neu starten**:
   ```bash
   ../web_restart.sh
   ```

### Für neue Installationen:
- Keine zusätzlichen Schritte erforderlich
- Das Schema wird automatisch bei der Installation erstellt

## Technische Details

### Dateien

#### Neue Dateien:
- `server_update_scheduler.py` - Scheduler für automatische Update-Prüfungen
- `database_migration_server_updates.sql` - SQL-Migration für bestehende Datenbanken
- `UPDATE_SYSTEM_README.md` - Diese Dokumentation

#### Geänderte Dateien:
- `database.py` - Erweiterte GameServer-Klasse mit Update-Feldern
- `steam_utils.py` - Neue Methoden: `check_for_server_update()`, `download_server_update()`
- `server_manager.py` - Zurücksetzen der Update-Flags nach Server-Start
- `app.py` - ServerUpdateScheduler-Integration und neue API-Endpoints
- `templates/server_dashboard.html` - Update-Banner und JavaScript-Funktionen

### Wie es funktioniert

1. **Scheduler startet automatisch** beim Web-Interface-Start
2. **Alle 4 Stunden** wird für jeden installierten Server geprüft:
   - SteamCMD `app_update 223350 validate` wird ausgeführt
   - Wenn Updates verfügbar sind, werden sie heruntergeladen
   - Datenbank-Flags `update_available` und `update_downloaded` werden gesetzt
3. **Dashboard lädt** und prüft Update-Status via API
4. **Update-Banner** wird angezeigt, wenn Updates verfügbar sind
5. **Admin klickt** auf "Jetzt neu starten"
6. **Server startet neu** und wendet das Update an
7. **Update-Flags** werden zurückgesetzt

### SteamCMD Update-Check Logik

```python
# Prüft via SteamCMD
steamcmd +force_install_dir <path> +login <user> <pass> +app_update 223350 validate +quit

# Analysiert die Ausgabe:
# - "downloading" oder "update" → Update verfügbar
# - "Success" ohne Downloads → Kein Update
# - "fully installed" → Installation/Update abgeschlossen
```

## Fehlerbehandlung

### Häufige Probleme:

**Problem**: Update-Check schlägt fehl
- **Lösung**: Steam-Zugangsdaten in den Einstellungen prüfen

**Problem**: Banner wird nicht angezeigt
- **Lösung**: Seite neu laden (F5) oder Browser-Cache leeren

**Problem**: APScheduler nicht verfügbar
- **Lösung**: `pip install apscheduler` im venv ausführen

**Problem**: Datenbank-Migration fehlgeschlagen
- **Lösung**: SQL-Datei manuell mit sqlite3 ausführen

## Logs

### Scheduler-Logs:
```bash
tail -f /pfad/zu/gameserver-webinterface/webinterface.log
```

**Beispiel-Ausgabe:**
```
INFO:server_update_scheduler:Server Update Scheduler initialized
INFO:server_update_scheduler:Server auto-update check task scheduled (every 4 hours)
INFO:server_update_scheduler:Starting server update check task...
INFO:server_update_scheduler:Checking 3 server(s) for updates...
INFO:server_update_scheduler:Checking server: My DayZ Server (ID: 1)
INFO:server_update_scheduler:Update available for My DayZ Server: Update was available and has been downloaded
INFO:server_update_scheduler:Update check completed: 3 checked, 1 updates found, 0 errors
```

## Konfiguration

### Scheduler-Intervall ändern:

In `server_update_scheduler.py`:
```python
# Aktuell: 240 Minuten (4 Stunden)
trigger=IntervalTrigger(minutes=240)

# Beispiel für 2 Stunden:
trigger=IntervalTrigger(minutes=120)
```

## Sicherheit

- **Credentials**: Steam-Zugangsdaten werden aus der Datenbank gelesen
- **Automatischer Download**: Nur für installierte Server
- **Manuelle Anwendung**: Admin muss Server manuell neu starten
- **Keine Auto-Restarts**: Server werden NICHT automatisch neu gestartet

## Support

Bei Problemen:
1. Web-Interface-Logs prüfen: `webinterface.log`
2. SteamCMD manuell testen: `steamcmd +login <user> <pass> +app_update 223350 validate +quit`
3. Datenbank-Schema prüfen: `sqlite3 gameserver.db ".schema game_servers"`

## Lizenz

Teil des DayZ GameServer Web-Interface Projekts
