from html import escape
import io
import os
import textwrap
from typing import Optional
from uuid import uuid4

import loader
from loader import auth, admin

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, InlineQueryHandler
from telegram.constants import ParseMode
from hugchat import hugchat
from deepl import Translator, TextResult
from deepgram import Deepgram

from user_data import UserData

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_RESPONSE_TRIES = 5
LANG_NAMES: str = '\n'.join(['BG - Bulgarian', 'CS - Czech', 'DA - Danish', 'DE - German', 'EL - Greek', 'EN-GB - English (British)', 'EN-US - English (American)', 'ES - Spanish', 'ET - Estonian', 'FI - Finnish', 'FR - French', 'HU - Hungarian', 'ID - Indonesian', 'IT - Italian', 'JA - Japanese', 'KO - Korean', 'LT - Lithuanian', 'LV - Latvian', 'NB - Norwegian (Bokmål)', 'NL - Dutch', 'PL - Polish', 'PT-BR - Portuguese (Brazilian)', 'PT-PT - Portuguese (all other Portuguese varieties)', 'RO - Romanian', 'RU - Russian', 'SK - Slovak', 'SL - Slovenian', 'SV - Swedish', 'TR - Turkish', 'UK - Ukrainian', 'ZH - Chinese (simplified)'])
LANG_CODES = ['BG','CS','DA','DE','EL','EN-GB','EN-US','ES','ET','FI','FR','HU','ID','IT','JA','KO','LT','LV','NB','NL','PL','PT-BR','PT-PT','RO','RU','SK','SL','SV','TR','UK','ZH']



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
        message = f'Only gibberish as response even after {MAX_RESPONSE_TRIES} tries.. The model is probably overloaded.. Sorry :( You can try again though'
    return message


def reset_conversation(user_data: UserData, *, delete: bool) -> str:
    old_conversation_id = user_data.chatbot.current_conversation
    new_conversation_id = user_data.chatbot.new_conversation()
    user_data.chatbot.change_conversation(new_conversation_id)
    if delete:
        user_data.chatbot.delete_conversation(old_conversation_id)
    return old_conversation_id


def translate_text(text: str, target_lang: str, translator: Translator) -> tuple[str, str]:
    response = translator.translate_text(text, target_lang=target_lang)
    user_text = response.text if isinstance(response, TextResult) else response[0].text
    detected_source_lang = response.detected_source_lang if isinstance(response, TextResult) else response[0].detected_source_lang
    return user_text, detected_source_lang


def stt(audio: bytes) -> tuple[str, str]:
    config = loader.load_config()
    if not config.get('deepgram_api_token'):
        return '', ''
    dg = Deepgram(config['deepgram_api_token'])
    source = {'buffer': audio, 'mimetype': 'audio/ogg'}
    options = {'detect_language': True}
    response = dg.transcription.sync_prerecorded(source, options) # type: ignore
    transcript = response['results']['channels'][0]['alternatives'][0]['transcript'] # type: ignore
    detected_language = response['results']['channels'][0]['detected_language'] # type: ignore
    detected_language = 'EN-US' if detected_language == 'en' else detected_language.upper()
    return transcript, detected_language


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


async def prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_text = update.effective_message.text
    # translate to english
    if user_data.language and user_data.translator:
        user_text, detected_source_lang = translate_text(user_text, target_lang='EN-US', translator=user_data.translator)
        loader.log(update, title=f'translated from {detected_source_lang} to english', message=user_text)
    # get response from chatbot
    message = get_response(user_data.chatbot, user_data.temperature, user_text)
    # translate back to original language
    loader.log(update, title='hugchat', message=message)
    if user_data.language and user_data.translator:
        message, _ = translate_text(message, target_lang=user_data.language, translator=user_data.translator)
        loader.log(update, title=f'translated from english to {user_data.language}', message=message)
    # send response back to telegram
    message_wrap = textwrap.wrap(message, 3500, expand_tabs=False, replace_whitespace=False, break_long_words=False, break_on_hyphens=False)
    for part_index, part in enumerate(message_wrap):
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


async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no message
    if not update.effective_message or not update.effective_message.text:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Please specify a language like this: /translate [language]\n\npossible language codes:\n\n{LANG_NAMES}')
        return
    if context.args[0] == 'off':
        user_data = loader.update_user_data(update)
        user_data.language = None
        loader.update_user_data(update)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Translation disabled')
        return
    if not context.args[0].upper() in LANG_CODES:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Unrecognized language code: {context.args[0]}\n\npossible language codes:\n\n{LANG_NAMES}')
        return
    user_data = loader.update_user_data(update)
    if not user_data.translator:
        config = loader.load_config()
        if not config.get('deepl_api_token'):
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"This bot doesn't have a translator installed. Please ask the creator of the bot to add one.")
            return
        user_data.translator = Translator(config['deepl_api_token'])
    user_data.language = context.args[0].upper()
    loader.update_user_data(update)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Language set to {user_data.language}. You can now write in your language and it will be translated to english before the Chatbot sees it. The answer from the bot will then be translated back to your language. You can disable this with /translate off')


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


async def voice_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no voice message
    if not update.effective_message or not update.effective_message.voice:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    # get transcript
    file = await context.bot.get_file(update.effective_message.voice.file_id)
    with io.BytesIO() as audio:  # TODO i don't know if this is a good idea to just hold the whole file in memory
        await file.download_to_memory(audio)
        transcript, spoken_language = stt(audio.getvalue())
    if not transcript:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Could not transcribe voice message')
        return

    # translate transcript to english
    config = loader.load_config()
    if not config.get('deepl_api_token') and spoken_language != 'EN-US':
        error_text = f"The detected language is \"{spoken_language}\" but this bot doesn't have a translator installed. Please ask the creator of the bot to add one."
        await context.bot.send_message(chat_id=update.effective_chat.id, text=error_text)
        return
    translator = Translator(config['deepl_api_token'])
    transcript_translated = transcript if spoken_language == 'EN-US' else translate_text(transcript, 'EN-US', translator)[0]

    # get summary from chatbot
    chatbot = loader.new_chatbot()
    text_for_bot = (f"The following text is an automatic transcript of a voice message, so it might not have the best quality."
                    f" Please write a short summary of that text."
                    f" Answer with just the summary, no introductory words or anything."
                    f" Transcript:"
                    f"\n\n{transcript_translated}")
    message = get_response(chatbot, 0.9, text_for_bot)
    chatbot.delete_conversation(chatbot.current_conversation)

    # translate summary back to original language
    message_translated = message if spoken_language == 'EN-US' else translate_text(message, spoken_language, translator)[0]

    # send transcript and summary to telegram
    final_message = f'Summary{" (translated)" if spoken_language != "EN-US" else ""}:'
    final_message += f'\n{message_translated}'
    final_message += f'\n\nTranscript (detected language: {spoken_language}):'
    final_message += f'\n{transcript}'
    await context.bot.send_message(chat_id=update.effective_chat.id, text=final_message)


async def voice_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # user not whitelisted
    if not auth(update):
        return
    # no voice message
    if not update.effective_message or not update.effective_message.voice:
        return
    # no chat or user associated with update
    if not update.effective_chat or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    # get transcript
    file = await context.bot.get_file(update.effective_message.voice.file_id)
    with io.BytesIO() as audio:  # TODO i don't know if this is a good idea to just hold the whole file in memory
        await file.download_to_memory(audio)
        transcript, spoken_language = stt(audio.getvalue())
    if not transcript:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Could not transcribe voice message')
        return
    loader.log(update, title='voice message transcript', message=transcript)

    # translate transcript to english
    config = loader.load_config()
    if not config.get('deepl_api_token') and spoken_language != 'EN-US':
        error_text = f"The detected language is \"{spoken_language}\" but this bot doesn't have a translator installed. Please ask the creator of the bot to add one."
        await context.bot.send_message(chat_id=update.effective_chat.id, text=error_text)
        return
    translator = Translator(config['deepl_api_token'])
    transcript_translated = transcript if spoken_language == 'EN-US' else translate_text(transcript, 'EN-US', translator)[0]

    # get answer from chatbot
    user_data = loader.update_user_data(update)
    message = get_response(user_data.chatbot, user_data.temperature, transcript_translated)
    loader.log(update, title='hugchat', message=message)

    # send transcript and summary to telegram
    final_message = f'Transcript (detected language: {spoken_language}):'
    final_message += f'\n{transcript}'
    final_message += f'\n\nAnswer from bot:'
    final_message += f'\n{message}'
    await context.bot.send_message(chat_id=update.effective_chat.id, text=final_message)



# async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not update.inline_query or not update.inline_query.query:
#         return
#     results = [
#         InlineQueryResultArticle(
#             id=str(uuid4()),
#             title="Caps",
#             input_message_content=InputTextMessageContent(update.inline_query.query.upper()),
#         ),
#         InlineQueryResultArticle(
#             id=str(uuid4()),
#             title="Bold",
#             input_message_content=InputTextMessageContent(
#                 f"<b>{escape(update.inline_query.query)}</b>", parse_mode=ParseMode.HTML
#             ),
#         ),
#         InlineQueryResultArticle(
#             id=str(uuid4()),
#             title="Italic",
#             input_message_content=InputTextMessageContent(
#                 f"<i>{escape(update.inline_query.query)}</i>", parse_mode=ParseMode.HTML
#             ),
#         ),
#     ]

#     await update.inline_query.answer(results)
#     await context.bot.send_message(chat_id=update.effective_chat.id, text=update.inline_query.query.upper())
#     if update.message:
#         await update.message.reply_text(update.inline_query.query.upper())


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
    config = loader.load_config()
    if not config['telegram_api_token']:
        print('No telegram api token found. Please create a telegram bot and add the token to config.json')
        return
    app = ApplicationBuilder().token(config['telegram_api_token']).build()


    # Telegram Handlers

    # app.add_handler(MessageHandler(filters.TEXT, dev))

    # app.add_handler(InlineQueryHandler(inline_query))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('temp', temp))
    app.add_handler(CommandHandler('private', private))
    app.add_handler(CommandHandler('new', chatbot_new))
    app.add_handler(CommandHandler('delete', chatbot_delete))
    app.add_handler(CommandHandler('bottalk', bottalk))
    app.add_handler(CommandHandler('translate', translate))

    app.add_handler(CommandHandler('add', whitelist_add))
    app.add_handler(CommandHandler('remove', whitelist_remove))
    app.add_handler(CommandHandler('list', whitelist_list))

    app.add_handler(MessageHandler(filters.VOICE & filters.FORWARDED, voice_summary))
    app.add_handler(MessageHandler(filters.VOICE, voice_prompt))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.add_handler(MessageHandler(filters.TEXT, prompt))

    # Run
    print('starting polling..')
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()