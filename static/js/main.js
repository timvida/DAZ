// GameServer Manager - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(function(flash) {
        setTimeout(function() {
            flash.style.opacity = '0';
            setTimeout(function() {
                flash.remove();
            }, 300);
        }, 5000);
    });

    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(function(field) {
                if (!field.value.trim()) {
                    isValid = false;
                    field.style.borderColor = '#da3633';
                } else {
                    field.style.borderColor = '';
                }
            });

            if (!isValid) {
                e.preventDefault();
                alert('Please fill in all required fields');
            }
        });
    });

    // Password confirmation validation
    const confirmPasswordField = document.getElementById('confirm_password');
    if (confirmPasswordField) {
        const passwordField = document.getElementById('password');

        confirmPasswordField.addEventListener('input', function() {
            if (this.value !== passwordField.value) {
                this.setCustomValidity('Passwords do not match');
            } else {
                this.setCustomValidity('');
            }
        });

        passwordField.addEventListener('input', function() {
            if (confirmPasswordField.value) {
                confirmPasswordField.dispatchEvent(new Event('input'));
            }
        });
    }
});

// Refresh server status periodically
function refreshServerStatuses() {
    const serverCards = document.querySelectorAll('[data-server-id]');

    serverCards.forEach(function(card) {
        const serverId = card.getAttribute('data-server-id');

        fetch(`/api/server/${serverId}/status`)
            .then(response => response.json())
            .then(data => {
                // Update status badge
                const statusBadge = card.querySelector('.server-status');
                if (statusBadge) {
                    statusBadge.className = 'server-status status-' + data.status;
                    statusBadge.textContent = data.status;
                }

                // Update install badge
                const installBadge = card.querySelector('.badge');
                if (installBadge && data.is_installed) {
                    installBadge.className = 'badge badge-success';
                    installBadge.textContent = 'Yes';
                }
            })
            .catch(error => {
                console.error('Error refreshing server status:', error);
            });
    });
}

// Refresh every 10 seconds if on dashboard
if (document.querySelector('.servers-grid')) {
    setInterval(refreshServerStatuses, 10000);
}
