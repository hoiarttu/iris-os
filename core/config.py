"""
core/config.py — IRIS persistent config
Stores accent color, IMU bias, and other settings.
"""

import json, os

CONFIG_DIR  = os.path.expanduser('~/.iris')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
BIAS_PATH   = os.path.join(CONFIG_DIR, 'imu_bias.json')

DEFAULTS = {
    'accent': [80, 220, 255],   # IRIS cyan
}

def load_config() -> dict:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            # Fill missing keys with defaults
            for k, v in DEFAULTS.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return dict(DEFAULTS)

def save_config(data: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(data, f, indent=2)

def load_bias() -> dict:
    if os.path.exists(BIAS_PATH):
        try:
            with open(BIAS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return None

def save_bias(bias: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(BIAS_PATH, 'w') as f:
        json.dump(bias, f, indent=2)
