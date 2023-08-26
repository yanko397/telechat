import os
import json
import pickle

telegram_config_file = 'config.json'
allowed_users_file = 'allowed_users.json'
admins_file = 'admins.json'
chatbots_dir = 'chatbots'


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


def load_admins() -> list:
    if os.path.exists(admins_file):
        with open(admins_file, encoding='utf-8') as f:
            return json.load(f)
    else:
        return []


def load_user_data(user):
    path = os.path.join(chatbots_dir, f'{user}.pickle')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return pickle.load(f)
    else:
        return None


def save_user_data(user, user_data):
    path = os.path.join(chatbots_dir, f'{user}.pickle')
    os.makedirs(chatbots_dir, exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(user_data, f)
