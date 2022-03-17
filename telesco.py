import logging
import os
import time
import traceback
from functools import lru_cache

import requests
from aiogram import Bot, Dispatcher, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from async_lru import alru_cache
from mixpanel import Mixpanel

from strings import strings

token = os.environ['TELEGRAM_TOKEN']
MIXPANEL_TOKEN = os.environ.get('MIXPANEL_TOKEN')
CONNECTED_CHATS_JSON_URL = os.environ.get('CONNECTED_CHATS_JSON_URL')

if MIXPANEL_TOKEN:
    mp = Mixpanel(MIXPANEL_TOKEN)


@lru_cache()
def get_connected_chats(ttl_hash=None) -> dict:
    del ttl_hash  # to emphasize we don't use it and to shut pylint up
    if CONNECTED_CHATS_JSON_URL:
        connected_chats = requests.get(CONNECTED_CHATS_JSON_URL).json()
    else:
        connected_chats = {}
    return connected_chats


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=token)
dp = Dispatcher(bot)

available_langs = strings.keys()


@alru_cache()
async def get_chat_title(chat_id, ttl_hash=None):
    del ttl_hash  # to emphasize we don't use it and to shut pylint up
    try:
        return (await bot.get_chat(chat_id)).title
    except:
        return None


def get_ttl_hash(seconds=3600):
    """Return the same value withing `seconds` time period"""
    return round(time.time() / seconds)


MAX_DIMENSION = 640
MAX_DURATION = 60
MAX_SIZE = 8389000


def lang(message):
    if message.from_user.language_code:
        if message.from_user.language_code in available_langs:
            return message.from_user.language_code
    return 'en'


async def check_size(message):
    if message.video.file_size >= MAX_SIZE:
        await bot.send_message(message.chat.id,
                               strings[lang(message)]['size_handler'],
                               parse_mode='Markdown')
    return message.video.file_size < MAX_SIZE


async def check_duration(message):
    if message.video.duration > MAX_DURATION:
        await bot.send_message(message.chat.id,
                               strings[lang(message)]['duration_handler'],
                               parse_mode='Markdown')
    return message.video.duration <= MAX_DURATION


async def check_dimensions(message):
    if abs(message.video.height - message.video.width) not in {0, 1}:
        await bot.send_message(message.chat.id,
                               strings[lang(message)]['not_square'])
    if message.video.height > MAX_DIMENSION or message.video.width > MAX_DIMENSION:
        await bot.send_message(message.chat.id,
                               strings[lang(message)]['dimensions_handler'])
    return abs(message.video.height - message.video.width) in {0, 1}


async def get_kb(user_id):
    user_connected_chats = get_connected_chats(get_ttl_hash()).get(str(user_id))
    if user_connected_chats:
        kb = InlineKeyboardMarkup()
        for chat_id in user_connected_chats["chats"]:
            chat_name = await get_chat_title(chat_id, get_ttl_hash()) or str(chat_id)
            kb.add(InlineKeyboardButton(chat_name, callback_data='send-{}'.format(chat_id)))
        return kb


@dp.callback_query_handler(lambda call: True)
async def callback_buttons(call):
    if call.message and call.data:
        if call.data.startswith('send-'):
            send_chat_id = call.data.replace('send-', '')
            data = call.message.video_note.file_id
            try:
                m = await bot.send_video_note(chat_id=send_chat_id, video_note=data)
            except Exception as e:
                print('Error sending videonote', e)
                m = None
            # TODO: Localization
            if isinstance(m, Message):
                await bot.answer_callback_query(call.id, 'Отправлено ✅')
            else:
                await bot.answer_callback_query(call.id, 'Ошибка ❌')


@dp.message_handler(commands=['start'])
async def welcome(message):
    await bot.send_message(message.chat.id, strings[lang(message)]['start'].format(
        message.from_user.first_name, 'https://telegram.org/update'),
                           parse_mode='HTML', disable_web_page_preview=True)
    if MIXPANEL_TOKEN:
        mp.track(message.from_user.id, 'start', properties={'language': message.from_user.language_code})


@dp.message_handler(commands=['help'])
async def welcome(message):
    await bot.send_message(message.chat.id, strings[lang(message)]['help'],
                           parse_mode='HTML', disable_web_page_preview=False)
    if MIXPANEL_TOKEN:
        mp.track(message.from_user.id, 'help', properties={'language': message.from_user.language_code})


@dp.message_handler(content_types=['video', 'document', 'animation'])
async def converting(message):
    if message.content_type == 'video':
        if await check_size(message) and await check_dimensions(message) and await check_duration(message):
            try:
                await bot.send_chat_action(message.chat.id, 'record_video_note')
                videonote = await bot.download_file_by_id(message.video.file_id)
                if message.video.height < MAX_DIMENSION:
                    sent_note = await bot.send_video_note(message.chat.id, videonote, length=message.video.width)
                else:
                    sent_note = await bot.send_video_note(message.chat.id, videonote)
                if sent_note.content_type != 'video_note':
                    await bot.send_message(message.chat.id, strings[lang(message)]['error'])
                    try:
                        await bot.delete_message(sent_note.chat.id, sent_note.message_id)
                    except:
                        pass
                else:
                    kb = await get_kb(message.from_user.id)
                    if kb:
                        await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=sent_note.message_id,
                                                            reply_markup=kb)
                if MIXPANEL_TOKEN:
                    mp.track(message.from_user.id, 'convert',
                             properties={'language': message.from_user.language_code})
            except Exception as e:
                await bot.send_message(94026383, '`{}`'.format(e), parse_mode='Markdown')
                await bot.send_message(94026383, f"```{traceback.format_exc()}```", parse_mode='Markdown')
                await bot.forward_message(94026383, message.chat.id, message.message_id)  # some debug info
                await bot.send_message(message.chat.id, strings[lang(message)]['error'])
                if MIXPANEL_TOKEN:
                    mp.track(message.from_user.id, 'error', properties={'error': str(e)})
        return
    elif (message.content_type == 'document' and (message.document.mime_type == 'image/gif' or
                                                  message.document.mime_type == 'video/mp4')) or message.content_type == 'animation':
        await bot.send_message(message.chat.id, strings[lang(message)]['content_error'])
        return

    elif (message.content_type == 'document' and
          message.document.mime_type == 'video/webm'):
        await bot.send_message(message.chat.id, strings[lang(message)]['webm'], parse_mode='HTML')

    else:
        await bot.send_message(message.chat.id, strings[lang(message)]['content_error'])


@dp.message_handler(content_types=['text'])
async def text_handler(message):
    if message.content_type == 'text' and message.text != '/start' and message.text != '/help':
        await bot.send_message(message.chat.id, strings[lang(message)]['text_handler'])


@dp.message_handler(content_types=['video_note'])
async def video_note_handler(message):
    await bot.send_chat_action(message.chat.id, 'upload_video')
    try:
        await bot.send_video(message.chat.id, await bot.download_file_by_id(message.video_note.file_id))
    except Exception as e:
        await bot.send_message(message.chat.id, strings[lang(message)]['error'])
        if MIXPANEL_TOKEN:
            mp.track(message.from_user.id, 'error', properties={'error': str(e)})


if __name__ == '__main__':
    executor.start_polling(dp)
