import os
import threading
from datetime import datetime

import loader
from user_data import UserData

from hugchat import hugchat
from hugchat.login import Login

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COOKIE_PATH_DIR = 'cookies'
LOGDIR = 'logs'
MAX_TRIES = 5

lock = threading.Lock()

# don't access this directly to get a user, use update_user_data instead!
users: dict[str, UserData] = {}


def login():
    os.makedirs(COOKIE_PATH_DIR, exist_ok=True)
    cookies_files = os.listdir(COOKIE_PATH_DIR)
    if cookies_files:
        mail = cookies_files[0][:-5] if len(cookies_files) == 1 else input('Mail: ')
        sign = Login(mail, None)
        cookies = sign.loadCookiesFromDir(COOKIE_PATH_DIR)
    else:
        mail = input('Mail: ')
        pw = input('Password: ')
        sign = Login(mail, pw)
        cookies = sign.login()
        sign.saveCookiesToDir(COOKIE_PATH_DIR)
    return cookies.get_dict()


def new_chatbot():
    print('creating new chatbot! trying to login..')
    cookies = login()
    print('logged in! init chatbot..')
    chatbot = hugchat.ChatBot(cookies=cookies)
    print('chatbot ready!')
    return chatbot


def update_user_data(username: str, save=True) -> UserData:
    global users
    with lock:
        if username not in users:
            users[username] = loader.load_user_data(username) or UserData(new_chatbot())
        if save:
            loader.save_user_data(username, users[username])
    return users[username]


def admin(update: Update, warning=True):
    adminlist = loader.load_admins()
    allowed = update.effective_user.username in adminlist or update.effective_user.id in adminlist
    if warning and not allowed:
        print(f'not allowed user {update.effective_user.username or update.effective_user.id} tried to do admin stuff')
    return allowed


def auth(update: Update):
    if admin(update, warning=False):
        return True
    whitelist = loader.load_allowed_users()
    allowed = update.effective_user.username in whitelist or update.effective_user.id in whitelist
    if not allowed:
        print(f'not allowed user {update.effective_user.username or update.effective_user.id} tried to use bot')
    return allowed


def log(filename: str, message: str, title: str = None, update: Update = None):
    """Logs a message to a file in the LOGDIR directory.

    title is prioritized over update
    """
    full_name = (update.effective_user.first_name + ' ' + update.effective_user.last_name).strip() if update else None
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    title = title or update.effective_user.username or update.effective_user.id + (f' ({full_name})' if full_name else '')
    with lock:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, f'{filename}.log'), 'a', encoding='utf-8') as f:
            f.write(f'{timestamp} ================ {title} ================\n')
            f.write(f'{message}\n')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = update_user_data(update.effective_user.username)
    auth_text = 'You are whitelisted! have fun :D'
    not_auth_text = 'You are not whitelisted yet. Please ask the maker of this bot if you know them.'
    text = (f"[bot]\n"
            f"Hi I'm hugchat :) write anything\n\n"
            f"{auth_text if auth(update) else not_auth_text}\n\n"
            f"Current temperature is {user_data.temperature}\n"
            f"Update with: /temperature [temperature]")
    text += f"\n\nAdmin mode 🥳" if admin(update, warning=False) else ''
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username
    log(user, user, update.message.text)
    # user not whitelisted
    if not auth(update):
        return
    # no message
    if not update.message.text:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    # try to get a response from the chatbot
    user_data = update_user_data(user)
    tries_remaining = MAX_TRIES
    message = ''
    while not message and tries_remaining:
        try:
            message = user_data.chatbot.chat(update.message.text, temperature=user_data.temperature)
        except Exception as e:
            print(e)
            tries_remaining -= 1
    if not message and not tries_remaining:
        message = f'[bot]\nNur gibberish als Antwort auch nach {MAX_TRIES} Versuchen.. Sorry :( Kannst es aber gerne nochmal versuchen'
    # send response back to telegram
    log(user, 'hugchat', message)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_to_message_id=update.message.message_id)


async def temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    user = update.effective_user.username
    chat_id = update.effective_chat.id
    user_data = update_user_data(user)
    # no temperature given, send current temperature
    if not context.args:
        await context.bot.send_message(chat_id=chat_id, text=f'[bot]\nCurrent temperature is {user_data.temperature}\n\nUpdate with: /temperature [temperature]')
        return
    # invalid temperature, send error
    if not context.args[0].replace('.', '', 1).isdigit() or not 0 < float(context.args[0]) <= 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nInvalid temperature: {context.args[0]}')
        return
    # set temperature, send confirmation
    user_data.temperature = float(context.args[0])
    update_user_data(user)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nTemperature set to {user_data.temperature}')


def main():

    # Telegram
    config = loader.load_telegram_config()
    app = ApplicationBuilder().token(config['telegram_api_token']).build()

    # Telegram Handlers
    start_handler = CommandHandler('start', start)
    temperature_handler = CommandHandler('temperature', temperature)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), answer)

    app.add_handler(start_handler)
    app.add_handler(temperature_handler)
    app.add_handler(message_handler)

    # Run
    print('starting polling..')
    app.run_polling()


if __name__ == '__main__':
    main()