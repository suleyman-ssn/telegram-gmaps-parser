import os
import time  
import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

CHOOSING_LANGUAGE, CHOOSING_CATEGORY, CHOOSING_LOCATION = range(3)


class GoogleParser:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://maps.googleapis.com/maps/api/place'

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

    def nearby_search(self, query, lat, lng, language, radius_meters=5000):
        """Поиск по координатам (для поиска рядом)"""
        url = f'{self.base_url}/nearbysearch/json'
        params = {
            'location': f'{lat},{lng}',
            'radius': radius_meters,
            'keyword': query,
            'key': self.api_key,
            'language': language
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка при nearby search: {e}")
            return None

    def place_details(self, place_id, language):
        """Получение расширенных деталей"""
        url = f'{self.base_url}/details/json'
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_phone_number,formatted_address,website,rating,url,geometry',
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

    def next_page(self, token):
        """
        НОВЫЙ МЕТОД: Получение следующей страницы результатов
        """
        time.sleep(2)
        url = f'{self.base_url}/nearbysearch/json'
        params = {
            'pagetoken': token,
            'key': self.api_key
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка при next_page: {e}")
            return None


parser = GoogleParser(GOOGLE_API_KEY)



async def _build_results_keyboard(context: ContextTypes.DEFAULT_TYPE, results: list, lang: str) -> InlineKeyboardMarkup:
    """
    НОВАЯ ФУНКЦИЯ: Собирает клавиатуру с результатами и кнопками навигации.
    """
    places_keyboard = []
    
    for place in results[:20]:
        name = place.get('name', 'Unnamed')
        place_id = place['place_id']
        places_keyboard.append([
            InlineKeyboardButton(name, callback_data=f"details_{place_id}")
        ])

    nav_keyboard = []
    next_page_token = context.user_data.get('next_page_token')
    
    if next_page_token:
        nav_keyboard.append(
            InlineKeyboardButton(
                "Найти еще ⬇️" if lang == 'ru' else "Find More ⬇️",
                callback_data="find_more"
            )
        )
    
    nav_keyboard.append(
        InlineKeyboardButton(
            "Новый поиск 🔍" if lang == 'ru' else "New Search 🔍",
            callback_data="new_search"
        )
    )
    
    return InlineKeyboardMarkup(places_keyboard + [nav_keyboard])



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога: выбор языка."""
    context.user_data.clear()
    
    keyboard = [["Русский 🇷🇺", "English 🇬🇧"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "🌍 Please choose a language / Пожалуйста, выберите язык:",
        reply_markup=reply_markup
    )
    return CHOOSING_LANGUAGE


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: Выбран язык, спрашиваем категорию."""
    lang_text = update.message.text
    context.user_data['lang'] = 'ru' if "Рус" in lang_text else 'en'
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
    """Шаг 2: Выбрана категория. Спрашиваем место."""
    context.user_data['category'] = update.message.text
    lang = context.user_data['lang']

    if lang == 'ru':
        text = "🗺️ Теперь введите город (например, 'Париж') или отправьте свою геолокацию, чтобы найти рядом:"
        btn_text = "📍 Найти рядом со мной"
    else:
        text = "🗺️ Now enter a city (e.g., 'Paris') or send your location to find nearby:"
        btn_text = "📍 Find Near Me"

    keyboard = [[KeyboardButton(btn_text, request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder="Напр: Алматы")

    await update.message.reply_text(text, reply_markup=reply_markup)
    return CHOOSING_LOCATION


async def location_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Шаг 3: Получено место. Выполняем поиск и сохраняем результаты.
    """
    category = context.user_data['category']
    lang = context.user_data['lang']
    data = None

    if update.message.location:
        context.user_data['last_search_type'] = 'nearby'
        context.user_data['last_location'] = (update.message.location.latitude, update.message.location.longitude)
        
        loc = update.message.location
        await update.message.reply_text(
            "🔄 Ищу рядом с вами..." if lang == 'ru' else "🔄 Searching near you...",
            reply_markup=ReplyKeyboardRemove()
        )
        data = parser.nearby_search(category, loc.latitude, loc.longitude, lang)

    elif update.message.text:
        context.user_data['last_search_type'] = 'text'
        context.user_data['last_location'] = update.message.text
        
        full_location = update.message.text
        await update.message.reply_text(
            f"🔄 Начинаю поиск: '{category}' в '{full_location}'..." if lang == 'ru' else f"🔄 Searching for: '{category}' in '{full_location}'...",
            reply_markup=ReplyKeyboardRemove()
        )
        data = parser.text_search(category, full_location, lang)

    if not data or data.get('status') != 'OK' or not data.get('results'):
        msg = "❌ Ничего не найдено или ошибка API." if lang == 'ru' else "❌ Nothing found or API error."
        await update.message.reply_text(msg)
        return ConversationHandler.END

    context.user_data['last_results'] = data.get('results', [])
    context.user_data['next_page_token'] = data.get('next_page_token')

    results = context.user_data['last_results']
    if not results:
        msg = "❌ По вашему запросу ничего не найдено." if lang == 'ru' else "❌ Nothing found for your query."
        await update.message.reply_text(msg)
        return ConversationHandler.END
    
    reply_markup = await _build_results_keyboard(context, results, lang)
    msg = "✅ Вот что я нашел (нажмите для деталей):" if lang == 'ru' else "✅ Here's what I found (click for details):"
    await update.message.reply_text(msg, reply_markup=reply_markup)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога."""
    lang = context.user_data.get('lang', 'ru')
    msg = "❌ Операция отменена. Для нового поиска используйте /start" if lang == 'ru' else "❌ Operation cancelled. To start again, use /start"
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END



async def place_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Срабатывает при нажатии на место. Показывает детали + кнопку "Назад".
    ИЗМЕНЕНО: Сохраняет ID отправленной карты для последующего удаления.
    """
    query = update.callback_query
    await query.answer()

    place_id = query.data.split('_', 1)[1]
    lang = context.user_data.get('lang', 'ru')

    details = parser.place_details(place_id, lang)

    if not details or details.get('status') != 'OK':
        await query.edit_message_text(text="Ошибка получения деталей" if lang == 'ru' else "Error getting details")
        return

    result = details.get('result', {})
    name = result.get('name', '...')
    phone = result.get('formatted_phone_number', '')
    address = result.get('formatted_address', '')
    rating = result.get('rating', '')
    google_url = result.get('url', '')

    text_parts = [f"📍 *{name}*"]
    if rating: text_parts.append(f"⭐ {rating} / 5.0")
    if phone: text_parts.append(f"📞 `{phone}`")
    if address: text_parts.append(f"🗺️ {address}")

    message_text = "\n\n".join(text_parts)

    keyboard = []
    if google_url:
        keyboard.append([
            InlineKeyboardButton(
                "Открыть в Google Maps" if lang == 'ru' else "Open in Google Maps",
                url=google_url
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Назад к списку" if lang == 'ru' else "⬅️ Back to list",
            callback_data="back_to_list"
        )
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)

    
    old_map_msg_id = context.user_data.pop('last_map_message_id', None)
    if old_map_msg_id:
        try:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=old_map_msg_id)
        except Exception as e:
            print(f"Не удалось удалить старую карту: {e}")

    loc = result.get('geometry', {}).get('location', {})
    if loc:
        try:
            map_message = await query.message.reply_location(latitude=loc['lat'], longitude=loc['lng'])
            context.user_data['last_map_message_id'] = map_message.message_id
        except Exception as e:
            print(f"Не удалось отправить локацию: {e}")
    
    await query.edit_message_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )


async def back_to_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    НОВЫЙ ОБРАБОТЧИК: Возвращает к списку результатов.
    ИЗМЕНЕНО: Удаляет сообщение с картой при возврате.
    """
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data.get('lang', 'ru')
    results = context.user_data.get('last_results', [])

    map_msg_id = context.user_data.pop('last_map_message_id', None)
    if map_msg_id:
        try:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=map_msg_id)
        except Exception as e:
            print(f"Не удалось удалить карту: {e}")

    if not results:
        await query.edit_message_text("Ошибка: список результатов потерян. Начните новый поиск /start" if lang == 'ru' else "Error: results list lost. Start a new search /start")
        return

    reply_markup = await _build_results_keyboard(context, results, lang)
    msg = "✅ Вот что я нашел (нажмите для деталей):" if lang == 'ru' else "✅ Here's what I found (click for details):"
    
    await query.edit_message_text(text=msg, reply_markup=reply_markup)

async def find_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    НОВЫЙ ОБРАБОТЧИК: Загружает следующую страницу результатов.
    """
    query = update.callback_query
    lang = context.user_data.get('lang', 'ru')
    token = context.user_data.get('next_page_token')

    if not token:
        await query.answer(text="Больше результатов нет" if lang == 'ru' else "No more results", show_alert=True)
        return

    await query.answer(text="Загружаю..." if lang == 'ru' else "Loading...")
    
    data = parser.next_page(token)

    if not data or data.get('status') != 'OK' or not data.get('results'):
        await query.message.reply_text("Ошибка загрузки." if lang == 'ru' else "Error loading results.")
        context.user_data['next_page_token'] = None 
        return

    context.user_data['last_results'] = data.get('results', [])
    context.user_data['next_page_token'] = data.get('next_page_token')
    
    results = context.user_data['last_results']

    reply_markup = await _build_results_keyboard(context, results, lang)
    msg = "✅ Следующая страница результатов:" if lang == 'ru' else "✅ Next page of results:"
    
    await query.edit_message_text(text=msg, reply_markup=reply_markup)


async def new_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    НОВЫЙ ОБРАБОТЧИК: Предлагает начать новый поиск.
    """
    query = update.callback_query
    lang = context.user_data.get('lang', 'ru')
    await query.answer()

    msg = "Для нового поиска, отправьте команду /start" if lang == 'ru' else "To start a new search, send /start"
    
    await query.edit_message_text(text=msg)
    context.user_data.clear() 



def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_chosen)],
            CHOOSING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_chosen)],
            CHOOSING_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND | filters.LOCATION, location_chosen)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    
    application.add_handler(CallbackQueryHandler(back_to_list_callback, pattern=r'^back_to_list$'))
    application.add_handler(CallbackQueryHandler(find_more_callback, pattern=r'^find_more$'))
    application.add_handler(CallbackQueryHandler(new_search_callback, pattern=r'^new_search$'))
    application.add_handler(CallbackQueryHandler(place_details_callback, pattern=r'^details_'))
    
    application.add_handler(CommandHandler('cancel', cancel))

    print("✅ Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()