from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import os
from config import Config
from database import db, User, SteamAccount, GameServer, ServerMod, ServerScheduler
from steam_utils import SteamCMDManager
from server_manager import ServerManager
from update_manager import UpdateManager
from mod_manager import ModManager
from functools import wraps
from sqlalchemy import event
from sqlalchemy.engine import Engine
import atexit

# Import player tracking models (after db is initialized)
from player_models import Player, PlayerSession, PlayerName, PlayerIP
from player_event_models import PlayerEvent, PlayerStats, WebhookConfig

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)

# Set SQLite pragmas for better compatibility
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=DELETE")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA cache_size=10000")
    cursor.close()

# Initialize managers
steam_manager = SteamCMDManager()
server_manager = ServerManager()
update_manager = UpdateManager()
mod_manager = ModManager()

# Initialize schedulers (will be set up after app context is available)
mod_update_scheduler = None
server_update_scheduler = None
server_scheduler_manager = None
player_tracking_scheduler = None
adm_monitor_scheduler = None

# Context processor to add common data to all templates
@app.context_processor
def inject_common_data():
    """Inject common data into all templates"""
    data = {}
    if 'user_id' in session:
        # Add servers list for sidebar
        data['servers'] = server_manager.get_all_servers()
        # Add username
        user = User.query.get(session['user_id'])
        if user:
            data['username'] = user.username
    return data

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Installation required decorator
def installation_check(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if os.path.exists(Config.INSTALL_LOCK):
            return f(*args, **kwargs)
        return redirect(url_for('install'))
    return decorated_function


@app.route('/')
@installation_check
def index():
    """Redirect to dashboard or login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/install', methods=['GET', 'POST'])
def install():
    """Installation wizard"""
    # If already installed, redirect to login
    if os.path.exists(Config.INSTALL_LOCK):
        return redirect(url_for('login'))

    # Step tracking
    step = request.args.get('step', '1')

    if request.method == 'POST':
        if step == '1':
            # Step 1: Admin account creation
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            # Validation
            if not all([username, email, password, confirm_password]):
                flash('All fields are required', 'error')
                return render_template('install.html', step='1')

            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('install.html', step='1')

            if len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return render_template('install.html', step='1')

            # Store in session temporarily
            session['install_admin'] = {
                'username': username,
                'email': email,
                'password': password
            }

            return redirect(url_for('install', step='2'))

        elif step == '2':
            # Step 2: Steam account setup
            steam_username = request.form.get('steam_username')
            steam_password = request.form.get('steam_password')
            skip_verification = request.form.get('skip_verification')

            if not all([steam_username, steam_password]):
                flash('Steam credentials are required', 'error')
                return render_template('install.html', step='2')

            # Store Steam credentials
            session['install_steam'] = {
                'username': steam_username,
                'password': steam_password
            }

            # If skip verification, just continue
            if skip_verification:
                flash('Steam verification skipped. Credentials will be tested during first server installation.', 'info')
                return redirect(url_for('install', step='3'))

            # Otherwise verify (but this should be done via AJAX now)
            # This is a fallback if JavaScript is disabled
            success, message = steam_manager.verify_credentials(steam_username, steam_password)

            if not success:
                flash(f'{message} - You can skip verification and try later.', 'error')
                return render_template('install.html', step='2',
                                     steam_username=steam_username,
                                     verification_attempted=True)

            # Complete installation
            return redirect(url_for('install', step='3'))

        elif step == '3':
            # Finalize installation
            admin_data = session.get('install_admin')
            steam_data = session.get('install_steam')

            if not admin_data or not steam_data:
                flash('Installation data missing. Please start over.', 'error')
                session.pop('install_admin', None)
                session.pop('install_steam', None)
                return redirect(url_for('install', step='1'))

            try:
                # Ensure database is properly initialized with correct permissions
                db_path = os.path.join(Config.BASE_DIR, 'gameserver.db')
                old_umask = os.umask(0o002)
                try:
                    # Ensure all tables exist
                    db.create_all()

                    # Set proper permissions on database file
                    if os.path.exists(db_path):
                        os.chmod(db_path, 0o664)
                finally:
                    os.umask(old_umask)

                # Create admin user
                user = User(
                    username=admin_data['username'],
                    email=admin_data['email']
                )
                user.set_password(admin_data['password'])
                db.session.add(user)

                # Store Steam credentials
                steam_account = SteamAccount(
                    username=steam_data['username'],
                    password=steam_data['password'],
                    is_verified=True
                )
                db.session.add(steam_account)

                db.session.commit()

                # Create installation lock file
                with open(Config.INSTALL_LOCK, 'w') as f:
                    f.write('installed')

                # Clear session data
                session.pop('install_admin', None)
                session.pop('install_steam', None)

                flash('Installation completed successfully!', 'success')
                return redirect(url_for('login'))

            except Exception as e:
                db.session.rollback()
                flash(f'Installation failed: {str(e)}', 'error')
                return render_template('install.html', step='3')

    # GET request - show appropriate step
    return render_template('install.html', step=step)


@app.route('/login', methods=['GET', 'POST'])
@installation_check
def login():
    """Login page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@installation_check
@login_required
def dashboard():
    """Main dashboard"""
    servers = server_manager.get_all_servers()
    return render_template('dashboard.html', servers=servers, username=session.get('username'))


@app.route('/api/verify-steam', methods=['POST'])
def verify_steam():
    """AJAX endpoint for Steam credential verification"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({'success': False, 'message': 'Username and password required'}), 400

    # Verify credentials
    success, message = steam_manager.verify_credentials(username, password)

    return jsonify({'success': success, 'message': message})


@app.route('/server/create', methods=['POST'])
@installation_check
@login_required
def create_server():
    """Create a new DayZ server"""
    name = request.form.get('name')
    game_name = request.form.get('game_name')
    app_id = request.form.get('app_id')
    server_port = request.form.get('server_port')
    rcon_port = request.form.get('rcon_port')
    rcon_password = request.form.get('rcon_password')

    if not all([name, game_name, app_id, server_port, rcon_port, rcon_password]):
        flash('All fields are required', 'error')
        return redirect(url_for('dashboard'))

    try:
        app_id = int(app_id)
        server_port = int(server_port)
        rcon_port = int(rcon_port)

        server = server_manager.create_server(
            name=name,
            game_name=game_name,
            app_id=app_id,
            server_port=server_port,
            rcon_port=rcon_port,
            rcon_password=rcon_password
        )
        flash(f'DayZ Server "{name}" created successfully! Port: {server_port}, RCon Port: {rcon_port}', 'success')
    except Exception as e:
        flash(f'Error creating server: {str(e)}', 'error')

    return redirect(url_for('dashboard'))


@app.route('/server/<int:server_id>/install', methods=['POST'])
@installation_check
@login_required
def install_server(server_id):
    """Install/Update a server"""
    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    # Get Steam credentials
    steam_account = SteamAccount.query.first()
    if not steam_account:
        return jsonify({'success': False, 'message': 'Steam account not configured'}), 400

    # Update status
    server_manager.update_server_status(server_id, 'installing')

    # Install server (this should be done async in production)
    success, message = steam_manager.install_server(
        server.app_id,
        server.install_path,
        steam_account.username,
        steam_account.password
    )

    if success:
        server_manager.mark_server_installed(server_id)
        return jsonify({'success': True, 'message': message})
    else:
        server_manager.update_server_status(server_id, 'stopped')
        return jsonify({'success': False, 'message': message}), 500


@app.route('/server/<int:server_id>/start', methods=['POST'])
@installation_check
@login_required
def start_server(server_id):
    """Start a server"""
    success, message = server_manager.start_server(server_id)
    return jsonify({'success': success, 'message': message})


@app.route('/server/<int:server_id>/stop', methods=['POST'])
@installation_check
@login_required
def stop_server(server_id):
    """Stop a server"""
    success, message = server_manager.stop_server(server_id)
    return jsonify({'success': success, 'message': message})


@app.route('/server/<int:server_id>/delete', methods=['POST'])
@installation_check
@login_required
def delete_server(server_id):
    """Delete a server"""
    success, message = server_manager.delete_server(server_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('dashboard'))


@app.route('/api/server/<int:server_id>/status')
@installation_check
@login_required
def server_status(server_id):
    """Get server status"""
    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    status_info = steam_manager.get_server_status(server.install_path)

    return jsonify({
        'id': server.id,
        'name': server.name,
        'status': server.status,
        'is_installed': server.is_installed,
        'install_info': status_info
    })


@app.route('/api/server/<int:server_id>/update/check', methods=['POST'])
@installation_check
@login_required
def check_server_update(server_id):
    """Manually check for server updates"""
    success, message, update_available = server_update_scheduler.check_single_server_update(server_id)
    return jsonify({
        'success': success,
        'message': message,
        'update_available': update_available
    })


@app.route('/api/server/<int:server_id>/update/status', methods=['GET'])
@installation_check
@login_required
def get_server_update_status(server_id):
    """Get the current update status of a server"""
    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    return jsonify({
        'update_available': server.update_available or False,
        'update_downloaded': server.update_downloaded or False,
        'last_update_check': server.last_update_check.isoformat() if server.last_update_check else None
    })


@app.route('/server/<int:server_id>/dashboard')
@installation_check
@login_required
def server_dashboard(server_id):
    """Server-specific dashboard"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    username = User.query.get(session['user_id']).username
    return render_template('server_dashboard.html', server=server, username=username, server_id=server_id)


@app.route('/server/<int:server_id>/config')
@installation_check
@login_required
def server_config(server_id):
    """Server configuration page"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    config_content = server_manager.get_server_config(server_id)
    username = User.query.get(session['user_id']).username
    return render_template('server_config.html', server=server, config=config_content, username=username, server_id=server_id)


@app.route('/api/server/<int:server_id>/restart', methods=['POST'])
@installation_check
@login_required
def restart_server(server_id):
    """Restart a server"""
    success, message = server_manager.restart_server(server_id)
    return jsonify({'success': success, 'message': message})


@app.route('/api/server/<int:server_id>/console', methods=['GET'])
@installation_check
@login_required
def get_server_console(server_id):
    """Get server console output"""
    lines = request.args.get('lines', 100, type=int)
    log_content = server_manager.read_server_log(server_id, lines)
    return jsonify({'content': log_content})


@app.route('/api/server/<int:server_id>/config', methods=['GET', 'POST'])
@installation_check
@login_required
def api_server_config(server_id):
    """Get or update server configuration"""
    if request.method == 'GET':
        config = server_manager.get_server_config(server_id)
        if config is None:
            return jsonify({'success': False, 'message': 'Config not found'}), 404
        return jsonify({'success': True, 'config': config})

    elif request.method == 'POST':
        config_content = request.json.get('config')
        if not config_content:
            return jsonify({'success': False, 'message': 'No config content provided'}), 400

        success, message = server_manager.update_server_config(server_id, config_content)
        return jsonify({'success': success, 'message': message})


@app.route('/system/console')
@installation_check
@login_required
def system_console():
    """View web interface console log"""
    username = User.query.get(session['user_id']).username
    return render_template('system_console.html', username=username)


@app.route('/api/system/console', methods=['GET'])
@installation_check
@login_required
def get_system_console():
    """Get web interface console output"""
    lines = request.args.get('lines', 100, type=int)
    log_path = os.path.join(Config.BASE_DIR, 'webinterface.log')

    if not os.path.exists(log_path):
        return jsonify({'content': 'No log file found. Start the web interface using ./web_start.sh to create logs.'})

    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            content = ''.join(all_lines[-lines:])
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'content': f'Error reading log: {str(e)}'})


@app.route('/api/update/check', methods=['GET'])
@installation_check
@login_required
def check_updates():
    """Check for available updates"""
    result = update_manager.check_for_updates()
    return jsonify(result)


@app.route('/api/update/perform', methods=['POST'])
@installation_check
@login_required
def perform_update():
    """Perform the update"""
    success, message = update_manager.perform_update()

    if success:
        # Schedule restart after response is sent
        import threading
        def delayed_restart():
            import time
            time.sleep(2)  # Wait 2 seconds before restarting
            update_manager.restart_application()

        threading.Thread(target=delayed_restart).start()

    return jsonify({'success': success, 'message': message})


@app.route('/api/update/version', methods=['GET'])
@installation_check
@login_required
def get_version():
    """Get current version"""
    version = update_manager.get_current_version()
    return jsonify({'version': version})


# ============================================
# MOD MANAGEMENT ROUTES
# ============================================

@app.route('/server/<int:server_id>/mods')
@installation_check
@login_required
def server_mods(server_id):
    """Server mods management page"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    # Scan for new mods
    mod_manager.scan_server_mods(server_id)

    # Get all mods
    mods = mod_manager.get_server_mods(server_id)

    username = User.query.get(session['user_id']).username
    return render_template('server_mods.html', server=server, mods=mods, username=username, server_id=server_id)


@app.route('/api/server/<int:server_id>/mods/scan', methods=['POST'])
@installation_check
@login_required
def scan_mods(server_id):
    """Scan server for mods"""
    success, message, count = mod_manager.scan_server_mods(server_id)
    return jsonify({'success': success, 'message': message, 'count': count})


@app.route('/api/server/<int:server_id>/mods', methods=['GET'])
@installation_check
@login_required
def get_mods(server_id):
    """Get all mods for a server"""
    mods = mod_manager.get_server_mods(server_id)
    mods_data = [{
        'id': mod.id,
        'name': mod.mod_name,
        'folder': mod.mod_folder,
        'workshop_id': mod.workshop_id,
        'type': mod.mod_type,
        'is_active': mod.is_active,
        'auto_update': mod.auto_update,
        'keys_copied': mod.keys_copied,
        'file_size': mod.file_size,
        'last_updated': mod.last_updated.isoformat() if mod.last_updated else None
    } for mod in mods]
    return jsonify({'success': True, 'mods': mods_data})


@app.route('/api/mod/<int:mod_id>/toggle', methods=['POST'])
@installation_check
@login_required
def toggle_mod(mod_id):
    """Toggle mod active status"""
    data = request.get_json()
    active = data.get('active', False)
    success, message = mod_manager.toggle_mod(mod_id, active)
    return jsonify({'success': success, 'message': message})


@app.route('/api/mod/<int:mod_id>/type', methods=['POST'])
@installation_check
@login_required
def update_mod_type(mod_id):
    """Update mod type (client/server)"""
    data = request.get_json()
    mod_type = data.get('type')
    success, message = mod_manager.update_mod_type(mod_id, mod_type)
    return jsonify({'success': success, 'message': message})


@app.route('/api/server/<int:server_id>/mods/workshop', methods=['POST'])
@installation_check
@login_required
def add_workshop_mod(server_id):
    """Add a mod from Steam Workshop"""
    data = request.get_json()
    workshop_id = data.get('workshop_id')

    if not workshop_id:
        return jsonify({'success': False, 'message': 'Workshop ID is required'}), 400

    success, message = mod_manager.add_workshop_mod(server_id, workshop_id)
    return jsonify({'success': success, 'message': message})


@app.route('/api/mod/<int:mod_id>/update', methods=['POST'])
@installation_check
@login_required
def update_mod_route(mod_id):
    """Update a workshop mod"""
    success, message = mod_manager.update_mod(mod_id)
    return jsonify({'success': success, 'message': message})


@app.route('/api/mod/<int:mod_id>/delete', methods=['POST'])
@installation_check
@login_required
def delete_mod(mod_id):
    """Delete a mod"""
    success, message = mod_manager.remove_mod(mod_id, delete_files=True)
    return jsonify({'success': success, 'message': message})


@app.route('/api/mod/<int:mod_id>/auto-update', methods=['POST'])
@installation_check
@login_required
def toggle_auto_update(mod_id):
    """Toggle auto-update for a mod"""
    data = request.get_json()
    auto_update = data.get('auto_update', False)

    mod = ServerMod.query.get(mod_id)
    if not mod:
        return jsonify({'success': False, 'message': 'Mod not found'}), 404

    if not mod.workshop_id:
        return jsonify({'success': False, 'message': 'Auto-update only available for Workshop mods'}), 400

    try:
        mod.auto_update = auto_update
        db.session.commit()
        status = "enabled" if auto_update else "disabled"
        return jsonify({'success': True, 'message': f'Auto-update {status}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# ============================================
# SCHEDULER MANAGEMENT ROUTES
# ============================================

@app.route('/server/<int:server_id>/schedulers')
@installation_check
@login_required
def server_schedulers(server_id):
    """Server schedulers management page"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    # Get all schedulers for this server
    schedulers = server_scheduler_manager.get_server_schedulers(server_id)

    username = User.query.get(session['user_id']).username
    return render_template('server_schedulers.html', server=server, schedulers=schedulers, username=username, server_id=server_id)


@app.route('/api/server/<int:server_id>/schedulers', methods=['GET', 'POST'])
@installation_check
@login_required
def api_server_schedulers(server_id):
    """Get or create schedulers for a server"""
    if request.method == 'GET':
        schedulers = server_scheduler_manager.get_server_schedulers(server_id)
        schedulers_data = []
        for sched in schedulers:
            import json
            sched_data = {
                'id': sched.id,
                'name': sched.name,
                'schedule_type': sched.schedule_type or 'cron',
                'action_type': sched.action_type,
                'is_active': sched.is_active,
                'last_run': sched.last_run.isoformat() if sched.last_run else None,
                'created_at': sched.created_at.isoformat()
            }

            # Add schedule-specific fields
            if sched.schedule_type == 'interval':
                sched_data['interval_minutes'] = sched.interval_minutes
            else:
                sched_data['hour'] = sched.hour
                sched_data['minute'] = sched.minute
                sched_data['weekdays'] = [int(d) for d in sched.weekdays.split(',')] if sched.weekdays else []

            # Add action-specific fields
            if sched.action_type == 'restart':
                sched_data['kick_all_players'] = sched.kick_all_players
                sched_data['kick_minutes_before'] = sched.kick_minutes_before
                sched_data['warning_minutes'] = json.loads(sched.warning_minutes) if sched.warning_minutes else []
            elif sched.action_type == 'message':
                sched_data['custom_message'] = sched.custom_message

            schedulers_data.append(sched_data)
        return jsonify({'success': True, 'schedulers': schedulers_data})

    elif request.method == 'POST':
        data = request.get_json()

        # Validate required fields
        if 'name' not in data or 'action_type' not in data:
            return jsonify({'success': False, 'message': 'Name and action_type are required'}), 400

        # Create scheduler with new format
        success, message, scheduler_id = server_scheduler_manager.add_scheduler(
            server_id=server_id,
            name=data['name'],
            action_type=data['action_type'],
            schedule_type=data.get('schedule_type', 'cron'),
            hour=data.get('hour'),
            minute=data.get('minute'),
            weekdays=data.get('weekdays', []),
            interval_minutes=data.get('interval_minutes'),
            kick_all_players=data.get('kick_all_players', True),
            kick_minutes_before=data.get('kick_minutes_before', 1),
            warning_minutes=data.get('warning_minutes', [60, 30, 15, 10, 5, 3, 2, 1]),
            custom_message=data.get('custom_message', ''),
            is_active=data.get('is_active', True)
        )

        if success:
            return jsonify({'success': True, 'message': message, 'scheduler_id': scheduler_id})
        else:
            return jsonify({'success': False, 'message': message}), 400


@app.route('/api/scheduler/<int:scheduler_id>', methods=['GET', 'PUT', 'DELETE'])
@installation_check
@login_required
def api_scheduler(scheduler_id):
    """Get, update, or delete a scheduler"""
    if request.method == 'GET':
        scheduler = server_scheduler_manager.get_scheduler(scheduler_id)
        if not scheduler:
            return jsonify({'success': False, 'message': 'Scheduler not found'}), 404

        import json
        scheduler_data = {
            'id': scheduler.id,
            'server_id': scheduler.server_id,
            'name': scheduler.name,
            'hour': scheduler.hour,
            'minute': scheduler.minute,
            'weekdays': [int(d) for d in scheduler.weekdays.split(',')],
            'action_type': scheduler.action_type,
            'kick_all_players': scheduler.kick_all_players,
            'kick_minutes_before': scheduler.kick_minutes_before,
            'warning_minutes': json.loads(scheduler.warning_minutes) if scheduler.warning_minutes else [],
            'custom_message': scheduler.custom_message,
            'is_active': scheduler.is_active,
            'last_run': scheduler.last_run.isoformat() if scheduler.last_run else None
        }
        return jsonify({'success': True, 'scheduler': scheduler_data})

    elif request.method == 'PUT':
        data = request.get_json()
        success, message = server_scheduler_manager.update_scheduler(scheduler_id, **data)
        return jsonify({'success': success, 'message': message})

    elif request.method == 'DELETE':
        success, message = server_scheduler_manager.delete_scheduler(scheduler_id)
        return jsonify({'success': success, 'message': message})


@app.route('/api/scheduler/<int:scheduler_id>/toggle', methods=['POST'])
@installation_check
@login_required
def toggle_scheduler(scheduler_id):
    """Toggle scheduler active status"""
    data = request.get_json()
    is_active = data.get('is_active', False)
    success, message = server_scheduler_manager.toggle_scheduler(scheduler_id, is_active)
    return jsonify({'success': success, 'message': message})


# ============================================
# RCON MANAGEMENT ROUTES
# ============================================

@app.route('/server/<int:server_id>/rcon')
@installation_check
@login_required
def server_rcon(server_id):
    """Server RCon console page"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    username = User.query.get(session['user_id']).username
    return render_template('server_rcon.html', server=server, username=username, server_id=server_id)


@app.route('/api/server/<int:server_id>/rcon/test', methods=['POST'])
@installation_check
@login_required
def test_rcon_connection(server_id):
    """Test RCon connection"""
    from rcon_utils import RConManager
    import glob
    import os

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    # Add debug info about BattlEye config
    be_config = RConManager.read_battleye_config(server)
    config_debug = {}

    if be_config:
        config_debug['be_config_found'] = True
        config_debug['config_file'] = be_config.get('_config_file', 'Unknown')
        config_debug['rcon_port'] = be_config.get('rcon_port', 'Not set')
        config_debug['rcon_ip'] = be_config.get('rcon_ip', 'Not set')
        config_debug['password_set'] = 'Yes' if be_config.get('rcon_password') else 'No'
        config_debug['password_length'] = be_config.get('_password_length', 0)

        # Show first few chars of password (for debugging)
        if be_config.get('rcon_password'):
            pw = be_config.get('rcon_password')
            config_debug['password_preview'] = f"{pw[:3]}***{pw[-2:]}" if len(pw) > 5 else f"{pw[0]}***"
    else:
        config_debug['be_config_found'] = False
        config_debug['be_path'] = server.be_path
        # Check what files exist
        if os.path.exists(server.be_path):
            pattern = os.path.join(server.be_path, 'beserver_x64*.cfg')
            files = glob.glob(pattern)
            pattern2 = os.path.join(server.be_path, 'BEServer_x64*.cfg')
            files.extend(glob.glob(pattern2))
            config_debug['config_files_found'] = [os.path.basename(f) for f in files if not f.endswith('.so')]
        else:
            config_debug['be_path_exists'] = False

    success, message, details = RConManager.test_connection(server)
    details['config_debug'] = config_debug

    return jsonify({'success': success, 'message': message, 'details': details})


@app.route('/api/server/<int:server_id>/rcon/players', methods=['GET'])
@installation_check
@login_required
def get_rcon_players(server_id):
    """Get online players via RCon"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    success, players, message = RConManager.get_players(server)
    return jsonify({'success': success, 'players': players, 'message': message})


@app.route('/api/server/<int:server_id>/rcon/command', methods=['POST'])
@installation_check
@login_required
def send_rcon_command(server_id):
    """Send custom RCon command"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    data = request.get_json()
    command = data.get('command', '')

    if not command:
        return jsonify({'success': False, 'message': 'Command is required'}), 400

    success, response = RConManager.execute_command(server, command)
    return jsonify({'success': success, 'response': response})


@app.route('/api/server/<int:server_id>/rcon/message', methods=['POST'])
@installation_check
@login_required
def send_rcon_message(server_id):
    """Send message to all players"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    data = request.get_json()
    message = data.get('message', '')

    if not message:
        return jsonify({'success': False, 'message': 'Message is required'}), 400

    success, response = RConManager.send_server_message(server, message)
    return jsonify({'success': success, 'message': response})


@app.route('/api/server/<int:server_id>/rcon/message/<player_id>', methods=['POST'])
@installation_check
@login_required
def send_rcon_private_message(server_id, player_id):
    """Send private message to a specific player"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    data = request.get_json()
    message = data.get('message', '')

    if not message:
        return jsonify({'success': False, 'message': 'Message is required'}), 400

    # Use send_private_message from RConManager
    try:
        with RConManager.get_rcon_connection(server) as rcon:
            success, msg = rcon.connect()
            if not success:
                return jsonify({'success': False, 'message': f'Failed to connect: {msg}'}), 500

            success, response = rcon.send_private_message(player_id, message)
            return jsonify({'success': success, 'message': f'Private message sent to player {player_id}' if success else response})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/api/server/<int:server_id>/rcon/kick/<player_id>', methods=['POST'])
@installation_check
@login_required
def kick_rcon_player(server_id, player_id):
    """Kick a specific player"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    success, response = RConManager.kick_player(server, player_id)
    return jsonify({'success': success, 'message': 'Player kicked' if success else response})


@app.route('/api/server/<int:server_id>/rcon/ban/<player_id>', methods=['POST'])
@installation_check
@login_required
def ban_rcon_player(server_id, player_id):
    """Ban a specific player"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    data = request.get_json() or {}
    minutes = data.get('minutes', 0)  # 0 = permanent ban
    reason = data.get('reason', 'Banned by admin')

    success, response = RConManager.ban_player(server, player_id, minutes, reason)
    return jsonify({'success': success, 'message': 'Player banned' if success else response})


@app.route('/api/server/<int:server_id>/rcon/lock', methods=['POST'])
@installation_check
@login_required
def lock_rcon_server(server_id):
    """Lock the server - no one can join"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    success, response = RConManager.lock_server(server)
    return jsonify({'success': success, 'message': 'Server locked' if success else response})


@app.route('/api/server/<int:server_id>/rcon/unlock', methods=['POST'])
@installation_check
@login_required
def unlock_rcon_server(server_id):
    """Unlock the server"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    success, response = RConManager.unlock_server(server)
    return jsonify({'success': success, 'message': 'Server unlocked' if success else response})


@app.route('/api/server/<int:server_id>/rcon/kickall', methods=['POST'])
@installation_check
@login_required
def kickall_rcon_players(server_id):
    """Kick all players from the server"""
    from rcon_utils import RConManager

    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    data = request.get_json() or {}
    reason = data.get('reason', 'Server Restart')

    success, response = RConManager.kick_all_players(server, reason)
    return jsonify({'success': success, 'message': response})


# ============================================
# PLAYER TRACKING ROUTES
# ============================================

@app.route('/server/<int:server_id>/players')
@installation_check
@login_required
def server_players(server_id):
    """Players list page for a server"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    return render_template('server_players.html', server=server)


@app.route('/server/<int:server_id>/player/<int:player_id>')
@installation_check
@login_required
def player_profile(server_id, player_id):
    """Individual player profile page"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    player = Player.query.get(player_id)
    if not player or player.server_id != server_id:
        flash('Player not found', 'error')
        return redirect(url_for('server_players', server_id=server_id))

    # Check ban status
    from ban_manager import BanManager
    ban_manager = BanManager(server)
    is_banned = ban_manager.is_banned(player.steam_id) if player.steam_id else False

    return render_template('player_profile.html', server=server, player=player, is_banned=is_banned)


@app.route('/api/server/<int:server_id>/players', methods=['GET'])
@installation_check
@login_required
def api_get_players(server_id):
    """Get all players for a server with optional search/filter"""
    search = request.args.get('search', '').strip()
    online_only = request.args.get('online_only', 'false').lower() == 'true'
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    # Base query
    query = Player.query.filter_by(server_id=server_id)

    # Filter by online status
    if online_only:
        query = query.filter_by(is_online=True)

    # Search filter
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Player.current_name.like(search_pattern),
                Player.steam_id.like(search_pattern),
                Player.guid.like(search_pattern),
                Player.dayztools_id.like(search_pattern)
            )
        )

    # Sorting: Online players first, then by total playtime
    query = query.order_by(
        Player.is_online.desc(),
        Player.total_playtime.desc()
    )

    # Get total count
    total = query.count()

    # Pagination
    players = query.limit(limit).offset(offset).all()

    # Format response
    players_data = []
    for player in players:
        players_data.append({
            'id': player.id,
            'dayztools_id': player.dayztools_id,
            'guid': player.guid,
            'steam_id': player.steam_id,
            'bohemia_id': player.bohemia_id,
            'current_name': player.current_name,
            'current_ip': player.current_ip,
            'is_online': player.is_online,
            'total_playtime': player.total_playtime,
            'session_count': player.session_count,
            'first_seen': player.first_seen.isoformat() if player.first_seen else None,
            'last_seen': player.last_seen.isoformat() if player.last_seen else None
        })

    return jsonify({
        'success': True,
        'total': total,
        'limit': limit,
        'offset': offset,
        'players': players_data
    })


@app.route('/api/server/<int:server_id>/player/<int:player_id>', methods=['GET'])
@installation_check
@login_required
def api_get_player_profile(server_id, player_id):
    """Get detailed player profile"""
    player = Player.query.get(player_id)

    if not player or player.server_id != server_id:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    # Get tracker for this server
    tracker = player_tracking_scheduler.get_tracker(server_id)
    if not tracker:
        return jsonify({'success': False, 'message': 'Player tracker not available'}), 500

    # Get player stats
    stats = tracker.get_player_stats(player_id)

    if not stats:
        return jsonify({'success': False, 'message': 'Could not load player stats'}), 500

    # Format sessions
    sessions_data = []
    for session in stats['sessions']:
        sessions_data.append({
            'id': session.id,
            'join_time': session.join_time.isoformat(),
            'leave_time': session.leave_time.isoformat() if session.leave_time else None,
            'duration': session.duration,
            'name_at_join': session.name_at_join,
            'ip_at_join': session.ip_at_join,
            'port_at_join': session.port_at_join
        })

    # Format name history
    names_data = []
    for name in stats['name_history']:
        names_data.append({
            'name': name.name,
            'first_seen': name.first_seen.isoformat(),
            'last_seen': name.last_seen.isoformat(),
            'usage_count': name.usage_count
        })

    # Format IP history
    ips_data = []
    for ip in stats['ip_history']:
        ips_data.append({
            'ip_address': ip.ip_address,
            'port': ip.port,
            'first_seen': ip.first_seen.isoformat(),
            'last_seen': ip.last_seen.isoformat(),
            'usage_count': ip.usage_count
        })

    return jsonify({
        'success': True,
        'player': {
            'id': player.id,
            'dayztools_id': player.dayztools_id,
            'guid': player.guid,
            'steam_id': player.steam_id,
            'bohemia_id': player.bohemia_id,
            'current_name': player.current_name,
            'current_ip': player.current_ip,
            'current_port': player.current_port,
            'is_online': player.is_online,
            'total_playtime': player.total_playtime,
            'session_count': player.session_count,
            'first_seen': player.first_seen.isoformat() if player.first_seen else None,
            'last_seen': player.last_seen.isoformat() if player.last_seen else None
        },
        'sessions': sessions_data,
        'name_history': names_data,
        'ip_history': ips_data
    })


@app.route('/api/server/<int:server_id>/player/<int:player_id>/ban', methods=['POST'])
@installation_check
@login_required
def api_ban_player(server_id, player_id):
    """Ban a player by adding their Steam ID to ban.txt"""
    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    player = Player.query.get(player_id)
    if not player or player.server_id != server_id:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    if not player.steam_id:
        return jsonify({'success': False, 'message': 'Player has no Steam ID'}), 400

    # Get ban reason from request
    data = request.get_json() or {}
    reason = data.get('reason', f'Banned by {session.get("username", "Admin")}')

    # Ban the player
    from ban_manager import BanManager
    ban_manager = BanManager(server)
    success, message = ban_manager.add_ban(player.steam_id, reason)

    if success:
        logger.info(f"Player {player.current_name} (Steam ID: {player.steam_id}) banned by {session.get('username', 'Admin')}")
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route('/api/server/<int:server_id>/player/<int:player_id>/unban', methods=['POST'])
@installation_check
@login_required
def api_unban_player(server_id, player_id):
    """Unban a player by removing their Steam ID from ban.txt"""
    server = server_manager.get_server(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Server not found'}), 404

    player = Player.query.get(player_id)
    if not player or player.server_id != server_id:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    if not player.steam_id:
        return jsonify({'success': False, 'message': 'Player has no Steam ID'}), 400

    # Unban the player
    from ban_manager import BanManager
    ban_manager = BanManager(server)
    success, message = ban_manager.remove_ban(player.steam_id)

    if success:
        logger.info(f"Player {player.current_name} (Steam ID: {player.steam_id}) unbanned by {session.get('username', 'Admin')}")
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route('/api/server/<int:server_id>/player/<int:player_id>/events', methods=['GET'])
@installation_check
@login_required
def api_get_player_events(server_id, player_id):
    """Get player events (deaths, kills, unconscious)"""
    player = Player.query.get(player_id)

    if not player or player.server_id != server_id:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    try:
        # Get player stats
        stats = PlayerStats.query.filter_by(player_id=player_id).first()

        # Get events (latest 50)
        events = PlayerEvent.query.filter_by(player_id=player_id).order_by(PlayerEvent.timestamp.desc()).limit(50).all()

        # Format events
        events_data = []
        for event in events:
            event_dict = event.to_dict()

            # Add killer/victim player name if applicable
            if event.killer_id:
                killer = Player.query.get(event.killer_id)
                event_dict['killer_player_name'] = killer.current_name if killer else event.killer_name

            events_data.append(event_dict)

        return jsonify({
            'success': True,
            'stats': stats.to_dict() if stats else {
                'total_kills': 0,
                'total_deaths': 0,
                'suicide_count': 0,
                'unconscious_count': 0,
                'kd_ratio': 0.0,
                'longest_kill_distance': 0.0,
                'longest_kill_weapon': None
            },
            'events': events_data
        })

    except Exception as e:
        logger.error(f"Error loading player events: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# =============================================================================
#                          WEBHOOK MANAGEMENT ROUTES
# =============================================================================

@app.route('/server/<int:server_id>/webhooks')
@installation_check
@login_required
def server_webhooks(server_id):
    """Webhook configuration page"""
    server = server_manager.get_server(server_id)
    if not server:
        flash('Server not found', 'error')
        return redirect(url_for('dashboard'))

    # Get or create webhook config
    webhook_config = WebhookConfig.query.filter_by(server_id=server_id).first()

    return render_template('server_webhooks.html', server=server, webhook_config=webhook_config)


@app.route('/api/server/<int:server_id>/webhooks', methods=['GET'])
@installation_check
@login_required
def api_get_webhook_config(server_id):
    """Get webhook configuration"""
    webhook_config = WebhookConfig.query.filter_by(server_id=server_id).first()

    if not webhook_config:
        return jsonify({
            'success': True,
            'config': {
                'server_id': server_id,
                'unconscious_webhook_url': '',
                'death_webhook_url': '',
                'suicide_webhook_url': '',
                'unconscious_enabled': False,
                'death_enabled': False,
                'suicide_enabled': False
            }
        })

    return jsonify({'success': True, 'config': webhook_config.to_dict()})


@app.route('/api/server/<int:server_id>/webhooks', methods=['POST'])
@installation_check
@login_required
def api_update_webhook_config(server_id):
    """Update webhook configuration"""
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    try:
        # Get or create webhook config
        webhook_config = WebhookConfig.query.filter_by(server_id=server_id).first()

        if not webhook_config:
            webhook_config = WebhookConfig(server_id=server_id)
            db.session.add(webhook_config)

        # Update URLs
        if 'unconscious_webhook_url' in data:
            webhook_config.unconscious_webhook_url = data['unconscious_webhook_url'] or None

        if 'death_webhook_url' in data:
            webhook_config.death_webhook_url = data['death_webhook_url'] or None

        if 'suicide_webhook_url' in data:
            webhook_config.suicide_webhook_url = data['suicide_webhook_url'] or None

        # Update toggles
        if 'unconscious_enabled' in data:
            webhook_config.unconscious_enabled = bool(data['unconscious_enabled'])

        if 'death_enabled' in data:
            webhook_config.death_enabled = bool(data['death_enabled'])

        if 'suicide_enabled' in data:
            webhook_config.suicide_enabled = bool(data['suicide_enabled'])

        db.session.commit()

        logger.info(f"Updated webhook config for server {server_id} by {session.get('username', 'Admin')}")

        return jsonify({'success': True, 'message': 'Webhook configuration updated', 'config': webhook_config.to_dict()})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating webhook config: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/api/server/<int:server_id>/webhooks/test', methods=['POST'])
@installation_check
@login_required
def api_test_webhook(server_id):
    """Test a webhook by sending a test message"""
    data = request.get_json()

    if not data or 'webhook_url' not in data or 'type' not in data:
        return jsonify({'success': False, 'message': 'Missing webhook_url or type'}), 400

    webhook_url = data['webhook_url']
    webhook_type = data['type']

    if not webhook_url:
        return jsonify({'success': False, 'message': 'Webhook URL is empty'}), 400

    try:
        from discord_webhook import DiscordWebhook
        from datetime import datetime

        # Create test embed based on type
        position = {'x': 12345.6, 'y': 7890.1, 'z': 15.3}
        timestamp = datetime.now().isoformat()

        if webhook_type == 'unconscious':
            embed = DiscordWebhook.create_unconscious_embed(
                player_name='TestPlayer',
                position=position,
                timestamp=timestamp
            )
        elif webhook_type == 'death':
            embed = DiscordWebhook.create_death_embed(
                player_name='TestVictim',
                cause='Killed by player',
                position=position,
                timestamp=timestamp,
                killer_name='TestKiller',
                weapon='M4-A1',
                distance=75.5
            )
        elif webhook_type == 'suicide':
            embed = DiscordWebhook.create_suicide_embed(
                player_name='TestPlayer',
                position=position,
                timestamp=timestamp
            )
        else:
            return jsonify({'success': False, 'message': 'Invalid webhook type'}), 400

        # Add test indicator to embed
        embed['title'] = '🧪 TEST - ' + embed['title']
        embed['footer'] = {'text': 'This is a test message from DayZ Server Events'}

        # Send webhook
        success = DiscordWebhook.send_webhook(webhook_url, embed)

        if success:
            return jsonify({'success': True, 'message': 'Test webhook sent successfully!'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send test webhook. Check URL and try again.'}), 400

    except Exception as e:
        logger.error(f"Error testing webhook: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# Initialize database
with app.app_context():
    # Ensure database file and directory have proper permissions
    db_path = os.path.join(Config.BASE_DIR, 'gameserver.db')
    db_dir = os.path.dirname(db_path)

    # Set umask to ensure database is created with rw-rw-r-- (664) permissions
    old_umask = os.umask(0o002)
    try:
        # Ensure directory is writable
        if os.path.exists(db_dir):
            os.chmod(db_dir, 0o755)

        # Create all tables
        db.create_all()

        # If database file was just created, ensure it has proper permissions
        if os.path.exists(db_path):
            os.chmod(db_path, 0o664)

        # Run automatic database migrations for schedulers
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if new columns exist in server_schedulers
            cursor.execute("PRAGMA table_info(server_schedulers)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'schedule_type' not in columns:
                cursor.execute("ALTER TABLE server_schedulers ADD COLUMN schedule_type VARCHAR(20) DEFAULT 'cron'")
                cursor.execute("UPDATE server_schedulers SET schedule_type = 'cron' WHERE schedule_type IS NULL")
                print("✓ Added 'schedule_type' column to database")

            if 'interval_minutes' not in columns:
                cursor.execute("ALTER TABLE server_schedulers ADD COLUMN interval_minutes INTEGER")
                print("✓ Added 'interval_minutes' column to database")

            # Check if new columns exist in game_servers (for auto-update system)
            cursor.execute("PRAGMA table_info(game_servers)")
            game_server_columns = [row[1] for row in cursor.fetchall()]

            if 'update_available' not in game_server_columns:
                cursor.execute("ALTER TABLE game_servers ADD COLUMN update_available BOOLEAN DEFAULT 0")
                print("✓ Added 'update_available' column to game_servers table")

            if 'update_downloaded' not in game_server_columns:
                cursor.execute("ALTER TABLE game_servers ADD COLUMN update_downloaded BOOLEAN DEFAULT 0")
                print("✓ Added 'update_downloaded' column to game_servers table")

            if 'last_update_check' not in game_server_columns:
                cursor.execute("ALTER TABLE game_servers ADD COLUMN last_update_check DATETIME")
                print("✓ Added 'last_update_check' column to game_servers table")

            # Note: Player tracking tables will be created automatically via db.create_all()
            # No manual migration needed as these are new tables

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Note: Database migration check: {e}")

    finally:
        # Restore original umask
        os.umask(old_umask)

    # Initialize and start the mod update scheduler
    from scheduler import ModUpdateScheduler
    mod_update_scheduler = ModUpdateScheduler(app, mod_manager)
    mod_update_scheduler.start_auto_update_task()

    # Initialize and start the server update scheduler (checks for DayZ server updates every 4 hours)
    from server_update_scheduler import ServerUpdateScheduler
    server_update_scheduler = ServerUpdateScheduler(app, steam_manager, server_manager)
    server_update_scheduler.start_auto_update_check()

    # Initialize and start the server scheduler manager
    from server_scheduler import ServerSchedulerManager
    server_scheduler_manager = ServerSchedulerManager(app)
    server_scheduler_manager.load_all_schedulers()

    # Initialize and start the player tracking scheduler (monitors player join/leave events)
    from player_tracking_scheduler import PlayerTrackingScheduler
    player_tracking_scheduler = PlayerTrackingScheduler(app, server_manager)
    player_tracking_scheduler.start_tracking()

    # Initialize and start the ADM monitor scheduler (monitors ADM logs for deaths/kills/unconscious)
    from adm_monitor_scheduler import ADMMonitorScheduler
    adm_monitor_scheduler = ADMMonitorScheduler(app, server_manager)
    adm_monitor_scheduler.start_monitoring()

    # Register cleanup on shutdown
    def shutdown_schedulers():
        if mod_update_scheduler:
            mod_update_scheduler.shutdown()
        if server_update_scheduler:
            server_update_scheduler.shutdown()
        if server_scheduler_manager:
            server_scheduler_manager.shutdown()
        if player_tracking_scheduler:
            player_tracking_scheduler.shutdown()
        if adm_monitor_scheduler:
            adm_monitor_scheduler.shutdown()
    atexit.register(shutdown_schedulers)


if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(Config.SERVERS_DIR, exist_ok=True)

    # Ensure management scripts are executable
    import stat
    scripts = ['web_start.sh', 'web_stop.sh', 'web_restart.sh', 'install.sh']
    for script in scripts:
        script_path = os.path.join(Config.BASE_DIR, script)
        if os.path.exists(script_path):
            try:
                os.chmod(script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755
            except Exception as e:
                print(f"Warning: Could not set permissions for {script}: {e}")

    # Run Flask app
    print(f"Starting GameServer Web Interface on {Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
