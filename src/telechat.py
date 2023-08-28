import os
import textwrap

import loader
from loader import auth, admin

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_RESPONSE_TRIES = 5


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    text = "Hi I'm a Chatbot :) write anything"
    if auth(update):
        user_data = loader.update_user_data(update.effective_user.id)
        text += f"\n\nYou are whitelisted! have fun :D"
        text += f"\n\nCurrent temperature is {str(user_data.temperature)}\nUpdate with: /temp [temperature]"
        text += f"\n\n*Admin mode* 🥳" if admin(update, warning=False) else ''
    else:
        text += f"\n\nYou are not whitelisted yet. Please ask the creator of this bot to add you if you know them."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loader.log(update)
    # user not whitelisted
    if not auth(update):
        return
    # no message
    if not update.message or not update.message.text:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    # try to get a response from the chatbot
    user_data = loader.update_user_data(update.effective_user.id)
    tries_remaining = MAX_RESPONSE_TRIES
    message = ''
    while not message and tries_remaining:
        try:
            message = str(user_data.chatbot.chat(update.message.text, temperature=user_data.temperature))
        except Exception as e:
            print(e)
            tries_remaining -= 1
    if not message and not tries_remaining:
        message = f'Nur gibberish als Antwort auch nach {MAX_RESPONSE_TRIES} Versuchen.. Sorry :( Kannst es aber gerne nochmal versuchen'
    # send response back to telegram
    loader.log(update, title='hugchat', message=message)
    for part in textwrap.wrap(message, 3500, expand_tabs=False, replace_whitespace=False, break_long_words=False, break_on_hyphens=False):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=part, reply_to_message_id=update.message.message_id)


async def temp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_data = loader.update_user_data(update.effective_user.id)
    # no temperature given, send current temperature
    if not context.args:
        await context.bot.send_message(chat_id=chat_id, text=f'Current temperature is {user_data.temperature}\n\nUpdate with: /temp [temperature]')
        return
    # invalid temperature, send error
    if not context.args[0].replace('.', '', 1).isdigit() or not 0 < float(context.args[0]) <= 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Invalid temperature: {context.args[0]}')
        return
    # set temperature, send confirmation
    user_data.temperature = float(context.args[0])
    loader.update_user_data(update.effective_user.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Temperature set to {user_data.temperature}')


async def chatbot_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = loader.update_user_data(update.effective_user.id)
    new_conversation_id = user_data.chatbot.new_conversation()
    user_data.chatbot.change_conversation(new_conversation_id)
    loader.update_user_data(update.effective_user.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Chatbot has been reset')


async def whitelist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not admin
    if not admin(update):
        return
    # no chat associated with update
    if not update.effective_chat:
        return
    # no user given, send error
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please specify a username or id like this: /add [user]')
        return
    # add user to whitelist, send confirmation
    added = loader.add_allowed_user(context.args[0])
    if added:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'User "{context.args[0]}" has been added to the whitelist')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'User "{context.args[0]}" is already whitelisted')


async def whitelist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not admin
    if not admin(update):
        return
    # no chat associated with update
    if not update.effective_chat:
        return
    # no user given, send error
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please specify a username or id like this: /remove [user]')
        return
    # remove user from whitelist, send confirmation
    removed = loader.remove_allowed_user(context.args[0])
    if removed:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'User "{context.args[0]}" has been removed from the whitelist')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'User "{context.args[0]}" was not whitelisted in the first place')


async def whitelist_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not admin
    if not admin(update):
        return
    # no chat associated with update
    if not update.effective_chat:
        return
    # list whitelist, send confirmation
    whitelist = '\n'.join(loader.load_allowed_users() or ['<empty>'])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Whitelisted users:\n\n{whitelist}')


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # no chat associated with update
    if not update.effective_chat:
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Unknown command')


def main():
    # Ensure logged in to hugchat
    loader.hugchat_login()

    # Telegram
    config = loader.load_telegram_config()
    if not config['telegram_api_token']:
        print('No telegram api token found. Please create a telegram bot and add the token to config.json')
        return
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