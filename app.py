import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import yt_dlp
from flask import Flask, request
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем Flask app
app = Flask(__name__)

# Глобальные переменные
application = None
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
temp_dir = "temp"

def create_application():
    """Создает и настраивает приложение бота"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не найден")
        return None
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # ИНИЦИАЛИЗИРУЕМ приложение
    app.initialize()
    
    return app

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [
        [InlineKeyboardButton("📥 Скачать видео", callback_data="download_info")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🤖 **Video Downloader Bot**\n\n"
        "Я могу скачать видео с:\n"
        "• YouTube\n• TikTok\n• Instagram\n• VK\n\n"
        "Просто отправьте мне ссылку на видео!"
    )
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    text = (
        "📖 **Как использовать:**\n"
        "1. Отправьте ссылку на видео\n"
        "2. Я скачаю его в максимальном качестве\n\n"
        "🔗 **Поддерживаемые платформы:**\n"
        "• YouTube\n• TikTok\n• Instagram\n• VK"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик инлайн кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "download_info":
        await query.message.reply_text("📥 Отправьте ссылку на видео")
    elif query.data == "help":
        await help_command(update, context)

def is_supported_url(url: str) -> bool:
    """Проверяет поддержку URL"""
    supported_domains = [
        'youtube.com', 'youtu.be', 
        'tiktok.com', 'vm.tiktok.com',
        'instagram.com', 
        'vk.com'
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in supported_domains)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_message = update.message.text.strip()
    
    if not user_message.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Пожалуйста, отправьте валидную ссылку на видео")
        return

    if not is_supported_url(user_message):
        await update.message.reply_text("❌ Этот тип ссылки не поддерживается")
        return

    # Отправляем сообщение о начале загрузки
    status_message = await update.message.reply_text("⏳ Скачиваю видео...")

    try:
        # Скачиваем видео
        file_path = await download_video(user_message)
        
        if file_path and os.path.exists(file_path):
            # Получаем размер файла
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # в MB
            
            caption = f"✅ **Видео скачано!**\n💾 Размер: {file_size:.1f}MB"
            
            # Отправляем видео
            await update.message.reply_video(
                video=open(file_path, 'rb'),
                caption=caption,
                supports_streaming=True,
                parse_mode='Markdown'
            )
            
            # Удаляем статус сообщение и временный файл
            await status_message.delete()
            os.remove(file_path)
            
        else:
            await status_message.edit_text("❌ Не удалось скачать видео. Попробуйте другую ссылку.")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {str(e)}")
        await status_message.edit_text("❌ Произошла ошибка. Попробуйте другую ссылку.")

async def download_video(url: str) -> str:
    """Скачивает видео с использованием yt-dlp"""
    # Создаем временную директорию
    os.makedirs(temp_dir, exist_ok=True)
    
    # Настройки для yt-dlp
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'quiet': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"Видео скачано: {filename}")
            return filename
    except Exception as e:
        logger.error(f"Ошибка скачивания: {str(e)}")
        return None

@app.route('/')
def home():
    return "🤖 Bot is running! Send /start to your bot.", 200

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик webhook от Telegram"""
    global application
    
    if application is None:
        logger.error("Application not initialized")
        return "Application not ready", 503
        
    try:
        # Получаем данные от Telegram
        json_data = request.get_json()
        if not json_data:
            return "No data", 400
            
        # Создаем объект Update
        update = Update.de_json(json_data, application.bot)
        
        # Обрабатываем update в отдельном потоке
        def process_update():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Теперь application инициализирован и должен работать
                loop.run_until_complete(application.process_update(update))
            except Exception as e:
                logger.error(f"Error processing update: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=process_update)
        thread.daemon = True
        thread.start()
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "error", 500

async def setup_webhook():
    """Настраивает webhook для бота"""
    global application
    
    if application is None:
        application = create_application()
        if application is None:
            return False
    
    try:
        # Получаем URL от Render
        render_url = os.getenv('RENDER_EXTERNAL_URL')
        if not render_url:
            logger.error("RENDER_EXTERNAL_URL not found")
            return False
            
        webhook_url = f"{render_url}/webhook"
        
        # Устанавливаем webhook
        await application.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )
        
        logger.info(f"Webhook установлен: {webhook_url}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при настройке webhook: {e}")
        return False

def initialize_bot():
    """Инициализирует бота при запуске"""
    global application
    
    logger.info("Инициализация бота...")
    
    # Создаем и инициализируем приложение
    application = create_application()
    if application is None:
        logger.error("Не удалось создать приложение бота")
        return
    
    # Настраиваем webhook
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(setup_webhook())
        loop.close()
        
        if success:
            logger.info("Бот успешно инициализирован и webhook настроен")
        else:
            logger.error("Не удалось настроить webhook")
            
    except Exception as e:
        logger.error(f"Ошибка инициализации: {e}")

# Инициализируем бота при импорте
initialize_bot()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
