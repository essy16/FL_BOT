import os
import telebot

API_KEY = os.getenv('TELEGRAM_API_KEY')

bot = telebot.TeleBot(BOT_TOKEN)
