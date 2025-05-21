#!/bin/bash

git clone --filter=blob:none --no-checkout https://github.com/dalab/da-gpustats-client.git /opt/gpustats-client
cd /opt/gpustats

# add "gpuwatch" user if it doesn't exist
if ! id "gpuwatch" &>/dev/null; then
    echo "Creating user gpuwatch..."
    useradd --system --no-create-home --shell /bin/bash gpuwatch
fi

# create a venv if none exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# install requirements
venv/bin/python -m pip install -U -r requirements.txt

# add service files
echo "Adding service files..."
cp gpustats.service /etc/systemd/system/
cp gpustats-update.service /etc/systemd/system/
cp gpustats-update.timer /etc/systemd/system/

# enable and start the service
echo "Enabling and starting the service..."
systemctl daemon-reload
systemctl enable --now gpustats.service gpustats-update.timer
