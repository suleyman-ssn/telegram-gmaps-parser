import os
import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = 'AIzaSyDpyTDK10xdMPhqCiTQgwP-yxACejunDgU'
TELEGRAM_TOKEN = '8271860669:AAFaiP_YuHfIamdN_Yt8nLXpC_SkuteiBwc'
CHOOSING_LANGUAGE, CHOOSING_CATEGORY, CHOOSING_COUNTRY, CHOOSING_CITY = range(4)


class GoogleParser:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://maps.googleapis.com/maps/api/place'

    def geocode(self, location_name):
        """Получает координаты по названию города"""
        url = f'https://maps.googleapis.com/maps/api/geocode/json'
        params = {
            'address': location_name,
            'key': self.api_key,
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'OK' and data['results']:
                loc = data['results'][0]['geometry']['location']
                return loc['lng'], loc['lat']
            return None
        except Exception as e:
            print(f"Ошибка при геокодировании: {e}")
            return None

    def text_search(self, query, location_name, language):
        """Поиск организаций по категории и городу"""
        url = f'{self.base_url}/textsearch/json'
        params = {
            'query': f'{query} in {location_name}',
            'key': self.api_key,
            'language': language
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка при text search: {e}")
            return None

    def place_details(self, place_id, language):
        """Получение телефона организации"""
        url = f'{self.base_url}/details/json'
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_phone_number',
            'key': self.api_key,
            'language': language
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка при details: {e}")
            return None


parser = GoogleParser(GOOGLE_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Русский 🇷🇺", "English 🇬🇧"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "🌍 Please choose a language / Пожалуйста, выберите язык:",
        reply_markup=reply_markup
    )
    return CHOOSING_LANGUAGE


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_text = update.message.text
    if "Рус" in lang_text:
        context.user_data['lang'] = 'ru'
    else:
        context.user_data['lang'] = 'en'

    lang = context.user_data['lang']

    if lang == 'ru':
        await update.message.reply_text(
            "🔍 Отлично! Введите категорию для поиска (например: аптека, кафе, автомойка):",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "🔍 Great! Enter a category to search for (e.g. pharmacy, car wash, cafe):",
            reply_markup=ReplyKeyboardRemove()
        )
    return CHOOSING_CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['category'] = update.message.text
    lang = context.user_data['lang']

    if lang == 'ru':
        await update.message.reply_text("Введите страну:")
    else:
        await update.message.reply_text("Enter the country:")

    return CHOOSING_COUNTRY


async def country_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['country'] = update.message.text
    lang = context.user_data['lang']

    if lang == 'ru':
        await update.message.reply_text("Теперь введите город:")
    else:
        await update.message.reply_text("Now enter the city:")

    return CHOOSING_CITY


async def city_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text
    country = context.user_data['country']
    category = context.user_data['category']
    lang = context.user_data['lang']

    full_location = f"{city}, {country}"

    if lang == 'ru':
        await update.message.reply_text(
            f"🔄 Начинаю поиск...\n\nКатегория: {category}\nМестоположение: {full_location}"
        )
    else:
        await update.message.reply_text(
            f"🔄 Starting search...\n\nCategory: {category}\nLocation: {full_location}"
        )

    data = parser.text_search(category, full_location, lang)

    if not data or data.get('status') != 'OK' or not data.get('results'):
        msg = "❌ Ничего не найдено или ошибка API." if lang == 'ru' else "❌ Nothing found or API error."
        await update.message.reply_text(msg)
        return ConversationHandler.END

    all_places = data['results']
    result_text = ""

    if lang == 'ru':
        result_text += f"✅ Найдено организаций: {len(all_places)}\n\n"
    else:
        result_text += f"✅ Found places: {len(all_places)}\n\n"

    for place in all_places:
        name = place.get('name', 'Без названия' if lang == 'ru' else 'Unnamed')
        place_id = place['place_id']

        details = parser.place_details(place_id, lang)
        phone = ""
        if details and details.get('status') == 'OK':
            phone = details['result'].get('formatted_phone_number', "")

        phone_line = f"📞 {phone}" if phone else ("📞 Телефон не указан" if lang == 'ru' else "📞 No phone listed")
        result_text += f"📍 {name}\n{phone_line}\n\n"

    max_length = 4000
    parts = [result_text[i:i + max_length] for i in range(0, len(result_text), max_length)]
    for part in parts:
        await update.message.reply_text(part)

    if lang == 'ru':
        await update.message.reply_text("Хотите выполнить новый поиск? Отправьте /start")
    else:
        await update.message.reply_text("Want to start a new search? Send /start")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('lang', 'ru')
    msg = "❌ Операция отменена. Для нового поиска используйте /start" if lang == 'ru' else "❌ Operation cancelled. To start again, use /start"
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_chosen)],
            CHOOSING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_chosen)],
            CHOOSING_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_chosen)],
            CHOOSING_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_chosen)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    print("✅ Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
