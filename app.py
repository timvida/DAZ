from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import os
from config import Config
from database import db, User, SteamAccount, GameServer
from steam_utils import SteamCMDManager
from server_manager import ServerManager
from update_manager import UpdateManager
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)

# Initialize managers
steam_manager = SteamCMDManager()
server_manager = ServerManager()
update_manager = UpdateManager()

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
    return render_template('server_dashboard.html', server=server, username=username)


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
    return render_template('server_config.html', server=server, config=config_content, username=username)


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


# Initialize database
with app.app_context():
    db.create_all()


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
