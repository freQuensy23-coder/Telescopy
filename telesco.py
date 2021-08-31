# -*- coding: utf-8 -*-
import os
import time
from functools import lru_cache
from io import BytesIO

import requests
import telebot
from mixpanel import Mixpanel
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from strings import strings

token = os.environ['TELEGRAM_TOKEN']
MIXPANEL_TOKEN = os.environ.get('MIXPANEL_TOKEN')
CONNECTED_CHATS_JSON_URL = os.environ.get('CONNECTED_CHATS_JSON_URL')

if MIXPANEL_TOKEN:
    mp = Mixpanel(MIXPANEL_TOKEN)

if CONNECTED_CHATS_JSON_URL:
    connected_chats = requests.get(CONNECTED_CHATS_JSON_URL).json()
else:
    connected_chats = {}

bot = telebot.AsyncTeleBot(token)

available_langs = strings.keys()

CHAT_TITLES_CACHE = {}


@lru_cache()
def get_chat_title(chat_id, ttl_hash=None):
    del ttl_hash  # to emphasize we don't use it and to shut pylint up
    try:
        return bot.get_chat(chat_id).wait().title
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


def check_size(message):
    if message.video.file_size >= MAX_SIZE:
        bot.send_message(message.chat.id,
                         strings[lang(message)]['size_handler'],
                         parse_mode='Markdown').wait()
    return message.video.file_size < MAX_SIZE


def check_duration(message):
    if message.video.duration > MAX_DURATION:
        bot.send_message(message.chat.id,
                         strings[lang(message)]['duration_handler'],
                         parse_mode='Markdown').wait()
    return message.video.duration <= MAX_DURATION


def check_dimensions(message):
    if abs(message.video.height - message.video.width) not in {0, 1}:
        bot.send_message(message.chat.id,
                         strings[lang(message)]['not_square']).wait()
    if message.video.height > MAX_DIMENSION or message.video.width > MAX_DIMENSION:
        bot.send_message(message.chat.id,
                         strings[lang(message)]['dimensions_handler']).wait()
    return abs(message.video.height - message.video.width) in {0, 1}


def get_kb(user_id):
    user_connected_chats = connected_chats.get(str(user_id))
    if user_connected_chats:
        kb = InlineKeyboardMarkup()
        for chat_id in user_connected_chats["chats"]:
            chat_name = get_chat_title(chat_id, get_ttl_hash()) or str(chat_id)
            kb.add(InlineKeyboardButton(chat_name, callback_data='send-{}'.format(chat_id)))
        return kb


@bot.callback_query_handler(func=lambda call: True)
def callback_buttons(call):
    if call.message and call.data:
        if call.data.startswith('send-'):
            send_chat_id = call.data.replace('send-', '')
            data = call.message.video_note.file_id
            try:
                m = bot.send_video_note(chat_id=send_chat_id, data=data).wait()
            except Exception as e:
                print('Error sending videonote', e)
                m = None
            # TODO: Localization
            if isinstance(m, telebot.types.Message):
                bot.answer_callback_query(call.id, 'Отправлено ✅')
            else:
                bot.answer_callback_query(call.id, 'Ошибка ❌')


@bot.message_handler(commands=['start'])
def welcome(message):
    task = bot.send_message(message.chat.id, strings[lang(message)]['start'].format(
        message.from_user.first_name, 'https://telegram.org/update'),
                            parse_mode='HTML', disable_web_page_preview=True)
    if MIXPANEL_TOKEN:
        mp.track(message.from_user.id, 'start', properties={'language': message.from_user.language_code})
    task.wait()


@bot.message_handler(commands=['help'])
def welcome(message):
    task = bot.send_message(message.chat.id, strings[lang(message)]['help'],
                            parse_mode='HTML', disable_web_page_preview=False)
    if MIXPANEL_TOKEN:
        mp.track(message.from_user.id, 'help', properties={'language': message.from_user.language_code})
    task.wait()


@bot.message_handler(content_types=['video', 'document', 'animation'])
def converting(message):
    if message.content_type is 'video':
        if check_size(message) and check_dimensions(message) and check_duration(message):
            try:
                action = bot.send_chat_action(message.chat.id, 'record_video_note')
                videonote = bot.download_file(bot.get_file(message.video.file_id).wait().file_path).wait()
                if message.video.height < MAX_DIMENSION:
                    sent_note = bot.send_video_note(message.chat.id, videonote, length=message.video.width).wait()
                else:
                    sent_note = bot.send_video_note(message.chat.id, videonote).wait()
                if sent_note.content_type != 'video_note':
                    bot.send_message(message.chat.id, strings[lang(message)]['error']).wait()
                    try:
                        bot.delete_message(sent_note.chat.id, sent_note.message_id).wait()
                    except:
                        pass
                else:
                    kb = get_kb(message.from_user.id)
                    if kb:
                        bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=sent_note.message_id,
                                                      reply_markup=kb)
                action.wait()
                if MIXPANEL_TOKEN:
                    mp.track(message.from_user.id, 'convert',
                             properties={'language': message.from_user.language_code})
            except Exception as e:
                # bot.send_message(me, '`{}`'.format(e), parse_mode='Markdown').wait()
                # bot.forward_message(me, message.chat.id, message.message_id).wait()  # some debug info
                bot.send_message(message.chat.id, strings[lang(message)]['error']).wait()
                if MIXPANEL_TOKEN:
                    mp.track(message.from_user.id, 'error', properties={'error': str(e)})
        return
    elif (message.content_type is 'document' and (message.document.mime_type == 'image/gif' or
                                                  message.document.mime_type == 'video/mp4')) or message.content_type is 'animation':
        bot.send_message(message.chat.id, strings[lang(message)]['content_error'])
        return

    elif (message.content_type is 'document' and
          message.document.mime_type == 'video/webm'):
        bot.send_message(message.chat.id, strings[lang(message)]['webm'], parse_mode='HTML').wait()

    else:
        bot.send_message(message.chat.id, strings[lang(message)]['content_error']).wait()


@bot.message_handler(content_types=['text'])
def text_handler(message):
    if message.content_type is 'text' and message.text != '/start' and message.text != '/help':
        bot.send_message(message.chat.id, strings[lang(message)]['text_handler']).wait()


@bot.message_handler(content_types=['video_note'])
def video_note_handler(message):
    bot.send_chat_action(message.chat.id, 'upload_video').wait()
    try:
        file_url = bot.get_file_url(message.video_note.file_id)
        video_content = requests.get(file_url).content
        bot.send_video(message.chat.id, BytesIO(video_content)).wait()
    except Exception as e:
        bot.send_message(message.chat.id, strings[lang(message)]['error']).wait()
        if MIXPANEL_TOKEN:
            mp.track(message.from_user.id, 'error', properties={'error': str(e)})


bot.polling(none_stop=True)
