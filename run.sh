
# create a venv if none exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    install requirements
    venv/bin/python -m pip install -r requirements.txt
fi

# run the script
echo "Running gpustats.py..."
venv/bin/python gpustats.py
