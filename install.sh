#!/bin/bash

set -e

# clone the repository if it doesn't exist
if [ ! -d "/opt/gpustats-client" ]; then
    echo "Cloning gpustats-client repository..."
    git clone --filter=blob:none --no-checkout https://github.com/dalab/da-gpustats-client.git /opt/gpustats-client
    git config --global --add safe.directory /opt/gpustats-client
    cd /opt/gpustats-client
else
    echo "Repository already exists. Pulling latest changes..."
    cd /opt/gpustats-client
    git fetch --all
    git reset --hard origin/main
fi

# generate .gpustatrc
if [ ! -f /opt/gpustats-client/.gpustatrc ]; then
    echo "Creating .gpustatrc..."
    default_machine_name=$(hostname -s)
    read -p "Enter machine name (${default_machine_name}): " machine_name
    read -p "Enter log interval in seconds (60): " log_interval
    read -p "Enter MongoDB username: " mongo_user
    read -p "Enter MongoDB password: " mongo_pw
    read -p "Enter MongoDB host (cake.da.inf.ethz.ch): " mongo_host
    read -p "Enter MongoDB port (38510): " mongo_port
    # set default values if not provided
    machine_name=${machine_name:-$default_machine_name}
    log_interval=${log_interval:-60}
    mongo_host=${mongo_host:-cake.da.inf.ethz.ch}
    mongo_port=${mongo_port:-38510}
    # create .gpustatrc file
    cat <<EOL > /opt/gpustats-client/.gpustatrc
[gpustat]
machine_name = $machine_name
log_interval = $log_interval
mongo_user = $mongo_user
mongo_pw = $mongo_pw
mongo_host = $mongo_host
mongo_port = $mongo_port
EOL
    echo "Created .gpustatrc file with the following content:"
    cat /opt/gpustats-client/.gpustatrc
else
    echo ".gpustatrc already exists. Skipping creation."
fi

# add "gpuwatch" user if it doesn't exist
if ! id "gpuwatch" &>/dev/null; then
    echo "Creating user gpuwatch..."
    useradd --system --no-create-home --shell /bin/bash gpuwatch
fi

# give "gpuwatch" user read-write access to the repository
chown -R gpuwatch:gpuwatch /opt/gpustats-client


# create a venv if none exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# install requirements
venv/bin/python -m pip install -U -r requirements.txt

# add service files
echo "Adding service files..."
cp ./services/gpustats.service /etc/systemd/system/
cp ./services/gpustats-update.service /etc/systemd/system/
cp ./services/gpustats-update.timer /etc/systemd/system/

# enable and start the service
echo "Enabling and starting the service..."
systemctl daemon-reload
systemctl enable --now gpustats.service gpustats-update.timer
systemctl start gpustats.service gpustats-update.timer
systemctl restart gpustats.service gpustats-update.timer
