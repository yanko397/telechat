import os
import textwrap

import loader
from loader import auth, admin

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler
from hugchat import hugchat

from user_data import UserData

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_RESPONSE_TRIES = 5


def get_response(chatbot: hugchat.ChatBot, temperature: float, text: str) -> str:
    # try to get a response from the chatbot
    tries_remaining = MAX_RESPONSE_TRIES
    message = ''
    while not message and tries_remaining:
        try:
            message = str(chatbot.chat(text, temperature=temperature))
        except Exception as e:
            print(e)
            tries_remaining -= 1
    if not message and not tries_remaining:
        message = f'Nur gibberish als Antwort auch nach {MAX_RESPONSE_TRIES} Versuchen.. Sorry :( Kannst es aber gerne nochmal versuchen'
    return message


def reset_conversation(user_data: UserData, *, delete: bool) -> str:
    old_conversation_id = user_data.chatbot.current_conversation
    new_conversation_id = user_data.chatbot.new_conversation()
    user_data.chatbot.change_conversation(new_conversation_id)
    if delete:
        user_data.chatbot.delete_conversation(old_conversation_id)
    return old_conversation_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    text = "Hi I'm a Chatbot :) write anything"
    if auth(update):
        user_data = loader.update_user_data(update)
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
    if not update.effective_message or not update.effective_message.text:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = loader.update_user_data(update)
    message = get_response(user_data.chatbot, user_data.temperature, update.effective_message.text)
    # send response back to telegram
    loader.log(update, title='hugchat', message=message)
    for part_index, part in enumerate(textwrap.wrap(message, 3500, expand_tabs=False, replace_whitespace=False, break_long_words=False, break_on_hyphens=False)):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=part, reply_to_message_id=update.effective_message.message_id if part_index == 0 else None)


async def temp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user_data = loader.update_user_data(update)
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
    loader.update_user_data(update)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Temperature set to {user_data.temperature}')


async def chatbot_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = loader.update_user_data(update)
    reset_conversation(user_data, delete=False)
    loader.update_user_data(update)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'New conversation was started, the old one is still on HuggingChat')


async def chatbot_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    user_data = loader.update_user_data(update)
    old_conversation_id = reset_conversation(user_data, delete=True)
    logs_deleted = False
    if context.args and context.args[0] == 'logs':
        logs_deleted = loader.delete_log(update.effective_user.id, old_conversation_id)
    loader.update_user_data(update)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Conversation has been deleted and a new one has been started' + ('\nand the logs have been deleted' if logs_deleted else '\nbut the logs have been kept'))


async def private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no message
    if not update.effective_message or not update.effective_message.text:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    text = update.effective_message.text.removeprefix('/private').strip()
    if not text:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please specify a message like this: /private [message]', reply_to_message_id=update.effective_message.message_id)
        return
    user_data = loader.update_user_data(update)
    old_conversation_id = reset_conversation(user_data, delete=False)
    message = get_response(user_data.chatbot, user_data.temperature, text)
    temp_conversation_id = user_data.chatbot.current_conversation
    user_data.chatbot.change_conversation(old_conversation_id)
    user_data.chatbot.delete_conversation(temp_conversation_id)
    for part_index, part in enumerate(textwrap.wrap(message, 3500, expand_tabs=False, replace_whitespace=False, break_long_words=False, break_on_hyphens=False)):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=part, reply_to_message_id=update.effective_message.message_id if part_index == 0 else None)


async def bottalk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no message
    if not update.effective_message or not update.effective_message.text:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    text = update.effective_message.text.removeprefix('/bottalk').strip()
    text = text[text.find(' '):].strip() if ' ' in text else ''
    iterations: int = int(context.args[0]) if context.args and context.args[0].isdigit() else 0
    if not iterations or not text:
        err = ('Please specify a message like this:\n/bottalk [iterations] [message]\n'
            'where [iterations] is a number that specifies how many messages will be exchanged overall - '
            'e.g. for "4" both bots would get to write 2 messages each. '
            'This happens completely outside of your current conversation.')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=err, reply_to_message_id=update.effective_message.message_id)
        return
    if iterations > 10:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please specify a number of iterations between 1 and 10', reply_to_message_id=update.effective_message.message_id)
        return

    chatbots: list[hugchat.ChatBot] = [loader.new_chatbot() for _ in range(2)]
    logfile = f'bottalk_{chatbots[0].current_conversation}_{chatbots[1].current_conversation}'
    loader.log(update, filename=logfile, message=text)

    last_message_id = update.effective_message.message_id
    for i in range(iterations):
        chatbot = chatbots[i % 2]
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        text = get_response(chatbot, 0.9, text)
        botname = f'Bot {i % 2 + 1}'
        telegram_text = f'[{botname} | Iteration {i + 1}/{iterations}]\n\n' + text
        loader.log(update, filename=logfile, message=text, title=botname)
        for part_index, part in enumerate(textwrap.wrap(telegram_text, 3500, expand_tabs=False, replace_whitespace=False, break_long_words=False, break_on_hyphens=False)):
            message = await context.bot.send_message(chat_id=update.effective_chat.id, text=part, reply_to_message_id=last_message_id if part_index == 0 else None)
            last_message_id = message.message_id

    for chatbot in chatbots:
        chatbot.delete_conversation(chatbot.current_conversation)


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


async def dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="dev is fiddling around - can't respond right now")


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
    private_handler = CommandHandler('private', private)
    chatbot_new_handler = CommandHandler('new', chatbot_new)
    chatbot_delete_handler = CommandHandler('delete', chatbot_delete)
    bottalk_handler = CommandHandler('bottalk', bottalk)

    whitelist_add_handler = CommandHandler('add', whitelist_add)
    whitelist_remove_handler = CommandHandler('remove', whitelist_remove)
    whitelist_list_handler = CommandHandler('list', whitelist_list)

    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), answer)
    unknown_handler = MessageHandler(filters.COMMAND, unknown)

    # dev_handler = MessageHandler(filters.TEXT, dev)
    # app.add_handler(dev_handler)

    app.add_handler(start_handler)
    app.add_handler(temp_handler)
    app.add_handler(private_handler)
    app.add_handler(chatbot_new_handler)
    app.add_handler(chatbot_delete_handler)
    app.add_handler(bottalk_handler)

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