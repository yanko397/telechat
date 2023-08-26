import os
import json
import pickle
import threading
from datetime import datetime
from getpass import getpass

from hugchat import hugchat
from hugchat.login import Login
from telegram import Update

from user_data import UserData

TELEGRAM_CONFIG_FILE = 'config.json'
ALLOWED_USERS_FILE = 'allowed_users.json'
ADMINS_FILE = 'admins.json'

HUGCHAT_COOKIE_DIR = 'hugchat_cookies'
CHATBOTS_DIR = 'chatbots'
LOG_DIR = 'logs'

lock = threading.Lock()
# don't access this directly to get a user, use update_user_data instead!
users: dict[str, UserData] = {}


def load_telegram_config() -> dict:
    if os.path.exists(TELEGRAM_CONFIG_FILE):
        with open(TELEGRAM_CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    else:
        return None


def load_allowed_users() -> list:
    if os.path.exists(ALLOWED_USERS_FILE):
        with open(ALLOWED_USERS_FILE, encoding='utf-8') as f:
            return json.load(f)
    else:
        return []


def add_allowed_user(user) -> bool:
    allowed_users = load_allowed_users()
    if user not in allowed_users:
        allowed_users.append(user)
        with open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(allowed_users, f, indent=4)
            return True
    return False


def remove_allowed_user(user) -> bool:
    allowed_users = load_allowed_users()
    if user in allowed_users:
        allowed_users.remove(user)
        with open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(allowed_users, f, indent=4)
            return True
    return False


def load_admins() -> list:
    if os.path.exists(ADMINS_FILE):
        with open(ADMINS_FILE, encoding='utf-8') as f:
            return json.load(f)
    else:
        return []


def load_user_data(user_id):
    path = os.path.join(CHATBOTS_DIR, f'{user_id}.pickle')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            return pickle.load(f)
    else:
        return None


def save_user_data(user_id, user_data):
    path = os.path.join(CHATBOTS_DIR, f'{user_id}.pickle')
    os.makedirs(CHATBOTS_DIR, exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(user_data, f)


def new_chatbot():
    print('creating new chatbot! trying to login to HuggingChat..')
    cookies = hugchat_login()
    print('logged in!')
    print('init chatbot..')
    chatbot = hugchat.ChatBot(cookies=cookies)
    print('chatbot ready!')
    return chatbot


def hugchat_login():
    os.makedirs(HUGCHAT_COOKIE_DIR, exist_ok=True)
    cookie_files = os.listdir(HUGCHAT_COOKIE_DIR)
    if cookie_files:
        if len(cookie_files) == 1:
            mail = cookie_files[0].removesuffix('.json')
        else:
            print('Multiple cookie files found:')
            for i, file in enumerate(cookie_files):
                print(f'{i}: {file}')
            while True:
                choice = input('Choose one by entering the number: ')
                if choice.isdigit() and 0 <= int(choice) < len(cookie_files):
                    mail = cookie_files[int(choice)].removesuffix('.json')
                    break
                else:
                    print(f'Invalid choice ({choice}), try again')
        sign = Login(mail, None)
        cookies = sign.loadCookiesFromDir(HUGCHAT_COOKIE_DIR)
    else:
        mail = input('Mail: ')
        pw = getpass()
        sign = Login(mail, pw)
        cookies = sign.login()
        sign.saveCookiesToDir(HUGCHAT_COOKIE_DIR)
    return cookies.get_dict()


def update_user_data(user_id: str, save=True) -> UserData:
    """Returns the user data for the given user id.

    This automatically pickles and unpickles the user data.
    Unpickling is only done if user is not in memory yet.
    Pickling is always done unless "save" is False.
    If the user does not exist yet, a new one is created.
    """
    global users
    with lock:
        if user_id not in users:
            users[user_id] = load_user_data(user_id) or UserData(new_chatbot())
        if save:
            save_user_data(user_id, users[user_id])
    return users[user_id]


def log(update: Update, *, filename: str = None, message: str = None, title: str = None):
    """Logs a message to a file in the LOGDIR directory.

    "title" is prioritized over "update"
    """
    first_name = update.effective_user.first_name or ''
    last_name = update.effective_user.last_name or ''
    name = f'{first_name} {last_name}'.strip() if update else ''
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    filename = filename or update.effective_user.id
    message = message or update.message.text
    title = title or update.effective_user.username or update.effective_user.id + (f' ({name})' if name else '')
    with lock:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, f'{filename}.log'), 'a', encoding='utf-8') as f:
            f.write(f'{timestamp} ================ {title} ================\n')
            f.write(f'{message}\n')
