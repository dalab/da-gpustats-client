#!/bin/sh
#
# gpustats-client unattended installer
# run with `bash -c "$(curl -fsSL https://raw.githubusercontent.com/dalab/da-gpustats-client/HEAD/install.sh)"`
#
# ---------------------------------------------------------------------

set -euo pipefail

# ───── configuration ────────────────────────────────────────────────────────────
REPO_URL="https://github.com/dalab/da-gpustats-client.git"
REPO_DIR="/opt/gpustats-client"
SERVICE_DIR="services"          # relative to REPO_DIR
VENV_DIR="$REPO_DIR/venv"
# ────────────────────────────────────────────────────────────────────────────────

# privilege-escalation wrapper
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""            # we are already root
else
    SUDO="sudo"
    # ask for the password up-front so later calls don’t interrupt the flow
    $SUDO -v
fi

echo "Installing gpustats-client into $REPO_DIR"

# ───── clone or update repository ───────────────────────────────────────────────
if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning repository"
    $SUDO git clone --quiet "$REPO_URL" "$REPO_DIR"
    # mark it as safe for later git access
    $SUDO git config --global --add safe.directory "$REPO_DIR"
else
    echo "Repository already exists. Pulling latest changes"
    $SUDO git -C "$REPO_DIR" fetch --quiet --all
    $SUDO git -C "$REPO_DIR" reset --quiet --hard origin/main
fi

# ───── create .gpustatrc if missing ────────────────────────────────────────────
if ! $SUDO test -f "$REPO_DIR/.gpustatrc"; then
    echo "Creating .gpustatrc"
    default_machine_name=$(hostname -s)

    read -r -p "Enter machine name [${default_machine_name}]: " machine_name
    read -r -p "Enter log interval in seconds [30]: " log_interval
    read -r -p "Enter MongoDB host [cake.da.inf.ethz.ch]: " mongo_host
    read -r -p "Enter MongoDB port [38510]: " mongo_port
    read -r -p "Enter MongoDB username: " mongo_user
    read -r -p "Enter MongoDB password: " mongo_pw

    # defaults
    machine_name=${machine_name:-$default_machine_name}
    log_interval=${log_interval:-30}
    mongo_host=${mongo_host:-cake.da.inf.ethz.ch}
    mongo_port=${mongo_port:-38510}

    # write file atomically
    cat <<EOL | $SUDO tee "$REPO_DIR/.gpustatrc" >/dev/null
[gpustat]
machine_name = $machine_name
log_interval = $log_interval
mongo_user   = $mongo_user
mongo_pw     = $mongo_pw
mongo_host   = $mongo_host
mongo_port   = $mongo_port
EOL
else
    echo ".gpustatrc already exists - skipping."
fi

# ───── ensure dedicated system user ─────────────────────────────────────────────
if ! id "gpuwatch" &>/dev/null; then
    echo "Creating system user 'gpuwatch'"
    $SUDO useradd --system --no-create-home --shell /usr/sbin/nologin gpuwatch
fi

# ───── virtual environment & dependencies ──────────────────────────────────────
if ! $SUDO test -d "$VENV_DIR"; then
    echo "Creating Python virtualenv"
    # check if python3-venv is installed
    if ! $SUDO dpkg -l | grep -q python3-venv; then
        echo "python3-venv not found. Pleas install it by running:"
        echo "  sudo apt install python3-venv"
        echo "and re-run the installer."
        exit 1
    fi
    $SUDO python3 -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies"
$SUDO "$VENV_DIR/bin/python" -m pip install --quiet --upgrade -r "$REPO_DIR/requirements.txt"

# ───── systemd service units ───────────────────────────────────────────────────
echo "Installing systemd units"
$SUDO install -m 644 "$REPO_DIR/$SERVICE_DIR/gpustats.service" /etc/systemd/system/
$SUDO install -m 644 "$REPO_DIR/$SERVICE_DIR/gpustats-update.timer" /etc/systemd/system/
$SUDO install -m 644 "$REPO_DIR/$SERVICE_DIR/gpustats-update.service" /etc/systemd/system/

# ───── ownership fix for runtime user ──────────────────────────────────────────
$SUDO chown -R gpuwatch:gpuwatch "$REPO_DIR"

# ───── enable & start services ─────────────────────────────────────────────────
echo "Enabling and starting services"
$SUDO systemctl daemon-reload
$SUDO systemctl enable gpustats.service gpustats-update.timer
$SUDO systemctl restart gpustats.service gpustats-update.timer

echo "Installation finished successfully ✅"
