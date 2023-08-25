import os
import logging
import pickle

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
LOGDIR = 'logs'
MAX_TRIES = 5

chatbots = {}
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
    print('creating new chatbot! trying to login..')
    cookies = login()
    print('logged in! init chatbot..')
    chatbot = hugchat.ChatBot(cookies=cookies)
    print('chatbot ready!')
    return chatbot


def get_chatbot(user):
    global chatbots
    if user not in chatbots:
        chatbots[user] = loader.load_chatbot(user)
        if not chatbots[user]:
            chatbots[user] = new_chatbot()
            loader.save_chatbot(user, chatbots[user])
    return chatbots[user]


def log(user, sender, message):
    # TODO this is not thread safe
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, f'{user}.log'), 'a', encoding='utf-8') as f:
        f.write(f'================{sender}================\n{message}\n')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"[bot]\nHi I'm hugchat :) write anything\n\nRight now you still need to be whitelisted to get a response though. I'll change that soon!\n\nCurrent temperature is {temperature}]\n\nUpdate with: /temperature [temperature]")


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username
    log(user, user, update.message.text)
    # user not whitelisted
    if user not in loader.load_allowed_users():
        print(f'not allowed user {user} tried to use bot')
        return
    # no message
    if not update.message.text:
        return
    # try to get a response from the chatbot
    chatbot = get_chatbot(user)
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
    # send response back to telegram
    log(user, 'hugchat', message)
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
    # set temperature
    temperature = float(context.args[0])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nTemperature set to {temperature}')


def main():

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