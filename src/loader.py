import os
import json
import pickle
import threading
from datetime import datetime
from getpass import getpass
from typing import Optional, Union

from hugchat import hugchat
from hugchat.login import Login
from telegram import Update

from user_data import UserData

TELEGRAM_CONFIG_FILE = 'config.json'
ALLOWED_USERS_FILE = 'allowed_users.json'
ADMINS_FILE = 'admins.json'

HUGCHAT_COOKIE_DIR = 'hugchat_cookies'
USERS_DIR = 'users'
LOG_DIR = 'logs'

lock = threading.Lock()
# don't access this directly to get a user, use update_user_data instead!
users: dict[int, UserData] = {}


def load_telegram_config() -> dict:
    if os.path.exists(TELEGRAM_CONFIG_FILE):
        with lock, open(TELEGRAM_CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    else:
        return {}


def load_allowed_users() -> list:
    if os.path.exists(ALLOWED_USERS_FILE):
        with lock, open(ALLOWED_USERS_FILE, encoding='utf-8') as f:
            return json.load(f)
    else:
        return []


def add_allowed_user(user: Union[int, str]) -> bool:
    user = str(user)
    allowed_users = load_allowed_users()
    if user not in allowed_users:
        allowed_users.append(user)
        with lock, open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(allowed_users, f, indent=4)
            return True
    return False


def remove_allowed_user(user: Union[int, str]) -> bool:
    user = str(user)
    allowed_users = load_allowed_users()
    if user in allowed_users:
        allowed_users.remove(user)
        with lock, open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(allowed_users, f, indent=4)
            return True
    return False


def load_admins() -> list:
    if os.path.exists(ADMINS_FILE):
        with lock, open(ADMINS_FILE, encoding='utf-8') as f:
            return json.load(f)
    else:
        return []


def load_user_data(user_id: int) -> Optional[UserData]:
    path = os.path.join(USERS_DIR, f'{str(user_id)}.pickle')
    if os.path.exists(path):
        with lock, open(path, 'rb') as f:
            return pickle.load(f)
    else:
        return None


def save_user_data(user_id: int, user_data: UserData) -> None:
    path = os.path.join(USERS_DIR, f'{str(user_id)}.pickle')
    os.makedirs(USERS_DIR, exist_ok=True)
    with lock, open(path, 'wb') as f:
        pickle.dump(user_data, f)


def new_chatbot() -> hugchat.ChatBot:
    with lock:
        cookies = hugchat_login()
    chatbot = hugchat.ChatBot(cookies=cookies)
    return chatbot


def hugchat_login() -> dict:
    os.makedirs(HUGCHAT_COOKIE_DIR, exist_ok=True)
    cookie_files = os.listdir(HUGCHAT_COOKIE_DIR)
    if cookie_files:
        if len(cookie_files) == 1:
            mail = cookie_files[0].removesuffix('.json')
        else:
            print('Multiple HuggingChat cookie files found:')
            for i, file in enumerate(cookie_files):
                print(f'{i}: {file}')
            while True:
                choice = input('Choose one by entering the number: ')
                if choice.isdigit() and 0 <= int(choice) < len(cookie_files):
                    mail = cookie_files[int(choice)].removesuffix('.json')
                    break
                else:
                    print(f'Invalid choice ({choice}), try again')
        sign = Login(mail, '')
        cookies = sign.loadCookiesFromDir(HUGCHAT_COOKIE_DIR)
    else:
        print('No HuggingChat cookie files found, please login to HuggingChat')
        mail = input('Mail: ')
        pw = getpass()
        sign = Login(mail, pw)
        cookies = sign.login()
        sign.saveCookiesToDir(HUGCHAT_COOKIE_DIR)
    return cookies.get_dict()


def update_user_data(user_id: int, save: bool = True) -> UserData:
    """Returns the user data for the given user id, essentially syncing it with the file system.

    This automatically pickles and unpickles the user data.
    Unpickling is only done if user is not in memory yet.
    Pickling is always done unless "save" is False.
    If the user does not exist yet, a new one is created.
    """
    global users
    if user_id not in users:
        users[user_id] = load_user_data(user_id) or UserData(new_chatbot())
    if save:
        save_user_data(user_id, users[user_id])
    return users[user_id]


def __find_log_subdir(user_id: int) -> Optional[str]:
    """Returns the name of the subdirectory in the LOG_DIR directory that belongs to the user or None if not existent."""
    if not os.path.exists(LOG_DIR):
        return None
    for subdir in os.listdir(LOG_DIR):
        if os.path.isdir(subdir) and subdir.startswith(str(user_id)):
            return subdir
    return None


def log(update: Update, *, filename: str = '', message: str = '', title: str = '', subdir: str = '') -> None:
    """Logs a message to a file in the LOGDIR directory.

    A subdirectory is created for each user.
    Its name starts with their user id, followed by any string (username by default).
    The filename in the subdir is the chat id followed by '.log'.

    If the subdir is the string 'None', no subdirectory is created.

    The optional function parameters take precedence over information from the update object.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # find best filename, title and message in parameters
    name = ''
    if update and update.effective_user:
        first_name = update.effective_user.first_name or ''
        last_name = update.effective_user.last_name or ''
        name = f'{first_name} {last_name}'.strip()
        subdir = subdir or __find_log_subdir(update.effective_user.id) or str(update.effective_user.id) + '_' + (update.effective_user.username or name)
        title = title or update.effective_user.username or str(update.effective_user.id) + (f' ({name})' if name else '')
    if update and update.message:
        message = message or update.message.text or ''
    if update and update.effective_chat:
        filename = filename or str(update.effective_chat.id)
    filename = filename or 'unknown.log'

    if subdir == 'None':
        subdir = ''

    with lock:
        os.makedirs(os.path.join(LOG_DIR, subdir), exist_ok=True)
        with open(os.path.join(LOG_DIR, subdir, f'{filename}.log'), 'a', encoding='utf-8') as f:
            f.write(f'{timestamp} ================ {title} ================\n')
            f.write(f'{message}\n')
