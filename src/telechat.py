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

cookie_path_dir = 'cookies'
logfile = 'log.txt'
chatbot = None


def login():
    os.makedirs(cookie_path_dir, exist_ok=True)
    cookies_files = os.listdir(cookie_path_dir)
    if cookies_files:
        mail = cookies_files[0][:-5] if len(cookies_files) == 1 else input('Mail: ')
        sign = Login(mail, None)
        cookies = sign.loadCookiesFromDir(cookie_path_dir)
    else:
        mail = input('Mail: ')
        pw = input('Password: ')
        sign = Login(mail, pw)
        cookies = sign.login()
        sign.saveCookiesToDir(cookie_path_dir)
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
    with open(logfile, 'a', encoding='utf-8') as f:
        f.write(f'================{sender}================\n{message}\n')


async def hugstart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hi I'm hugchat :) write anything\n\nRight now you still need to be whitelisted to get a response though. I'll change that soon!")


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log(update.effective_user.username, update.message.text)
    if update.effective_user.username not in loader.load_allowed_users():
        print(f'not allowed user {update.effective_user.username} tried to use bot')
        return
    if not update.message.text:
        return
    tries_remaining = 3
    message = ''
    while not message and tries_remaining:
        # print(f'trying to answer with {tries_remaining} tries left..')
        try:
            message = chatbot.chat(update.message.text, temperature=0.5)
        except Exception as e:
            print(e)
            tries_remaining -= 1
    if not message and not tries_remaining:
        message = '[Nur gibberish als Antwort auch nach 3 Versuchen.. Sorry :( Kannst es aber gerne nochmal versuchen]'
    log(f'to {update.effective_user.username}', message)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_to_message_id=update.message.message_id)


def main():
    global chatbot
    chatbot = new_chatbot()

    print('init telegram..')
    config = loader.load_telegram_config()
    app = ApplicationBuilder().token(config['telegram_api_token']).build()
    print('telegram ready!')

    print('adding handlers..')
    start_handler = CommandHandler('start', hugstart)
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), answer)

    app.add_handler(start_handler)
    app.add_handler(echo_handler)
    print('handlers ready!')

    print('starting polling..')
    app.run_polling()


if __name__ == '__main__':
    main()