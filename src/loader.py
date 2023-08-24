import os
import json

telegram_config_file = 'config.json'
allowed_users_file = 'allowed_users.json'


def load_telegram_config() -> dict:
    if os.path.exists(telegram_config_file):
        with open(telegram_config_file, encoding='utf-8') as f:
            return json.load(f)
    else:
        return None


def load_allowed_users() -> list:
    if os.path.exists(allowed_users_file):
        with open(allowed_users_file, encoding='utf-8') as f:
            return json.load(f)
    else:
        return []
