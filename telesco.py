# -*- coding: utf-8 -*-
import os
from io import BytesIO

# import cloudconvert
# import ujson
import requests
import telebot
from mixpanel import Mixpanel  # from botan import track

from strings import strings

token = os.environ['TELEGRAM_TOKEN']
MIXPANEL_TOKEN = os.environ.get('MIXPANEL_TOKEN')
if MIXPANEL_TOKEN:
    mp = Mixpanel(MIXPANEL_TOKEN)

bot = telebot.AsyncTeleBot(token)

available_langs = strings.keys()

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
        """if check_size(message):
            try:
                videonote = bot.download_file((((bot.get_file(message.document.file_id)).wait()).file_path)).wait()
                bot.send_chat_action(message.chat.id, 'record_video_note').wait()
                bot.send_video_note(message.chat.id, videonote).wait()
                track(botan_token, message.from_user.id, message, 'Convert')
            except:
                bot.send_message(message.chat.id, strings[lang(message)]['error']).wait()
                track(botan_token, message.from_user.id, message, 'Error')
        else:
            return"""

    elif (message.content_type is 'document' and
          message.document.mime_type == 'video/webm'):
        if False:  # if str(message.from_user.id) == me:
            """
            if check_size(message):
                try:
                    status = bot.send_message(
                        message.chat.id, 
                        strings[lang(message)]['downloading'],
                        parse_mode='HTML').wait()
                    api = cloudconvert.Api(cloud_convert_token)
                    process = api.convert({
                        'inputformat': 'webm',
                        'outputformat': 'mp4',
                        'input': 'download',
                        'save': True,
                        'file': 'https://api.telegram.org/file/bot{}/{}'.format(token,
                         (((bot.get_file(message.document.file_id)).wait()).file_path))
                    })
                    bot.edit_message_text(message.chat.id, strings[lang(message)]['converting'].format(0),
                                          status.chat.id,
                                          status.message_id,
                                          parse_mode='HTML').wait()
                    while True:
                        r = requests.get('https:{}'.format(process['url']))
                        percentage = ujson.loads(r.text)['percent']
                        bot.edit_message_text(strings[lang(message)]['converting'].format(percentage), status.chat.id,
                                              status.message_id,
                                              parse_mode='HTML').wait()
                        if percentage == 100:
                            break
                    bot.edit_message_text(strings[lang(message)]['uploading'].format(percentage), status.chat.id,
                                          status.message_id,
                                          parse_mode='HTML').wait()
                    process.wait()
                    bot.send_chat_action(message.chat.id, 'record_video_note').wait()
                    file = '{}_{}.mp4'.format(message.from_user.id, message.message_id)
                    process.download(file)
                    videonote = open(file, 'rb')
                    bot.delete_message(status.chat.id, status.message_id).wait()
                    bot.send_video_note(message.chat.id, videonote).wait()
                    videonote.close()
                    os.remove(file)
                except:
                    bot.send_message(message.chat.id, strings[lang(message)]['error']).wait()
                    # track(botan_token, message.from_user.id, message, 'Error')
            else:
                return
            """
        else:
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
