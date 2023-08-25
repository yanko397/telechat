import os
import logging

import loader

from hugchat import hugchat
from hugchat.login import Login

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# logging.basicConfig(
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     level=logging.INFO
# )

COOKIE_PATH_DIR = 'cookies'
LOGFILE = 'log.txt'
MAX_TRIES = 5

chatbot = None
temperature = 0.9


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
    print('trying to login..')
    cookies = login()
    print('logged in!')
    print('init chatbot..')
    chatbot = hugchat.ChatBot(cookies=cookies)
    print('chatbot ready!')
    return chatbot


def log(sender, message):
    # TODO this is not thread safe
    with open(LOGFILE, 'a', encoding='utf-8') as f:
        f.write(f'================{sender}================\n{message}\n')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"[bot]\nHi I'm hugchat :) write anything\n\nRight now you still need to be whitelisted to get a response though. I'll change that soon!\n\nCurrent temperature is {temperature}]\n\nUpdate with: /temperature [temperature]")


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log(update.effective_user.username, update.message.text)
    if update.effective_user.username not in loader.load_allowed_users():
        print(f'not allowed user {update.effective_user.username} tried to use bot')
        return
    if not update.message.text:
        return
    tries_remaining = MAX_TRIES
    message = ''
    while not message and tries_remaining:
        try:
            message = chatbot.chat(update.message.text, temperature=temperature)
        except Exception as e:
            print(e)
            tries_remaining -= 1
    if not message and not tries_remaining:
        message = f'[bot]\nNur gibberish als Antwort auch nach {MAX_TRIES} Versuchen.. Sorry :( Kannst es aber gerne nochmal versuchen'
    log(f'to {update.effective_user.username}', message)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_to_message_id=update.message.message_id)


async def set_temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global temperature
    # no temperature given
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nCurrent temperature is {temperature}\n\nUpdate with: /temperature [temperature]')
        return
    # invalid temperature
    if not context.args[0].replace('.', '', 1).isdigit() or not 0 < float(context.args[0]) <= 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nInvalid temperature: {context.args[0]}')
        return
    temperature = float(context.args[0])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nTemperature set to {temperature}')


def main():
    global chatbot

    # HuggingChat
    chatbot = new_chatbot()

    # Telegram
    config = loader.load_telegram_config()
    app = ApplicationBuilder().token(config['telegram_api_token']).build()

    # Telegram Handlers
    start_handler = CommandHandler('start', start)
    temperature_handler = CommandHandler('temperature', set_temperature)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), answer)

    app.add_handler(start_handler)
    app.add_handler(temperature_handler)
    app.add_handler(message_handler)

    # Run
    print('starting polling..')
    app.run_polling()


if __name__ == '__main__':
    main()