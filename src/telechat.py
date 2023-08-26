import os

import loader

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_RESPONSE_TRIES = 5


def admin(update: Update, warning=True):
    adminlist = loader.load_admins()
    allowed = update.effective_user.username in adminlist or update.effective_user.id in adminlist
    if warning and not allowed:
        print(f'not allowed user {update.effective_user.username or update.effective_user.id} tried to do admin stuff')
    return allowed


def auth(update: Update, ignore_admin=False):
    if not ignore_admin and admin(update, warning=False):
        return True
    whitelist = loader.load_allowed_users()
    allowed = update.effective_user.username in whitelist or update.effective_user.id in whitelist
    if not allowed:
        print(f'not allowed user {update.effective_user.username or update.effective_user.id} tried to use bot')
    return allowed


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = loader.update_user_data(update.effective_user.id)
    auth_text = 'You are whitelisted! have fun :D'
    not_auth_text = 'You are not whitelisted yet. Please ask the maker of this bot if you know them.'
    text = (f"[bot]\n"
            f"Hi I'm hugchat :) write anything\n\n"
            f"{auth_text if auth(update) else not_auth_text}\n\n"
            f"Current temperature is {user_data.temperature}\n"
            f"Update with: /temp [temperature]")
    text += f"\n\nAdmin mode 🥳" if admin(update, warning=False) else ''
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loader.log(update)
    # user not whitelisted
    if not auth(update):
        return
    # no message
    if not update.message.text:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    # try to get a response from the chatbot
    user_data = loader.update_user_data(update.effective_user.id)
    tries_remaining = MAX_RESPONSE_TRIES
    message = ''
    while not message and tries_remaining:
        try:
            message = user_data.chatbot.chat(update.message.text, temperature=user_data.temperature)
        except Exception as e:
            print(e)
            tries_remaining -= 1
    if not message and not tries_remaining:
        message = f'[bot]\nNur gibberish als Antwort auch nach {MAX_RESPONSE_TRIES} Versuchen.. Sorry :( Kannst es aber gerne nochmal versuchen'
    # send response back to telegram
    loader.log(update, title='hugchat', message=message)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, reply_to_message_id=update.message.message_id)


async def temp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    chat_id = update.effective_chat.id
    user_data = loader.update_user_data(update.effective_user.id)
    # no temperature given, send current temperature
    if not context.args:
        await context.bot.send_message(chat_id=chat_id, text=f'[bot]\nCurrent temperature is {user_data.temperature}\n\nUpdate with: /temp [temperature]')
        return
    # invalid temperature, send error
    if not context.args[0].replace('.', '', 1).isdigit() or not 0 < float(context.args[0]) <= 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nInvalid temperature: {context.args[0]}')
        return
    # set temperature, send confirmation
    user_data.temperature = float(context.args[0])
    loader.update_user_data(update.effective_user.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nTemperature set to {user_data.temperature}')


async def chatbot_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = loader.update_user_data(update.effective_user.id)
    user_data.chatbot = loader.new_chatbot()
    loader.update_user_data(update.effective_user.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nChatbot has been reset')


async def whitelist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not admin
    if not admin(update):
        return
    # no user given, send error
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nPlease specify a username or id like this: /add [user]')
        return
    # add user to whitelist, send confirmation
    added = loader.add_allowed_user(context.args[0])
    if added:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nUser "{context.args[0]}" has been added to the whitelist')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nUser "{context.args[0]}" is already whitelisted')


async def whitelist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not admin
    if not admin(update):
        return
    # no user given, send error
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nPlease specify a username or id like this: /remove [user]')
        return
    # remove user from whitelist, send confirmation
    removed = loader.remove_allowed_user(context.args[0])
    if removed:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nUser "{context.args[0]}" has been removed from the whitelist')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nUser "{context.args[0]}" was not whitelisted in the first place')


async def whitelist_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not admin
    if not admin(update):
        return
    # list whitelist, send confirmation
    whitelist = '\n'.join(loader.load_allowed_users() or ['<empty>'])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nWhitelisted users:\n{whitelist}')


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'[bot]\nUnknown command')


def main():
    # Ensure logged in to hugchat
    loader.hugchat_login()

    # Telegram
    config = loader.load_telegram_config()
    app = ApplicationBuilder().token(config['telegram_api_token']).build()

    # Telegram Handlers
    start_handler = CommandHandler('start', start)
    temp_handler = CommandHandler('temp', temp)
    chatbot_reset_handler = CommandHandler('reset', chatbot_reset)
    whitelist_add_handler = CommandHandler('add', whitelist_add)
    whitelist_remove_handler = CommandHandler('remove', whitelist_remove)
    whitelist_list_handler = CommandHandler('list', whitelist_list)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), answer)
    unknown_handler = MessageHandler(filters.COMMAND, unknown)

    app.add_handler(start_handler)
    app.add_handler(temp_handler)
    app.add_handler(chatbot_reset_handler)
    app.add_handler(whitelist_add_handler)
    app.add_handler(whitelist_remove_handler)
    app.add_handler(whitelist_list_handler)
    app.add_handler(message_handler)
    app.add_handler(unknown_handler)

    # Run
    print('starting polling..')
    app.run_polling()


if __name__ == '__main__':
    main()