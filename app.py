import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
import yt_dlp
from flask import Flask, request

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем Flask app
app = Flask(__name__)

# Глобальные переменные
bot_app = None
temp_dir = "temp"

def init_bot():
    """Инициализация бота"""
    global bot_app
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден")
        return None
    
    bot_app = Application.builder().token(token).build()
    
    # Регистрируем обработчики
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    
    return bot_app

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📥 Скачать видео", callback_data="download_info")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "🤖 **Video Downloader Bot**\n\nОтправьте ссылку на видео с YouTube, TikTok, Instagram или VK"
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📖 **Как использовать:**
1. Отправьте ссылку на видео
2. Я скачаю его в максимальном качестве

🔗 **Поддерживаемые платформы:**
• YouTube
• TikTok  
• Instagram
• VK
    """
    await update.message.reply_text(text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "download_info":
        text = "📥 Отправьте ссылку на видео"
        await query.message.reply_text(text)
    elif query.data == "help":
        await help_command(update, context)

def is_supported_url(url: str) -> bool:
    supported_domains = ['youtube.com', 'youtu.be', 'tiktok.com', 'vm.tiktok.com', 'instagram.com', 'vk.com']
    return any(domain in url.lower() for domain in supported_domains)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    
    if not user_message.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Отправьте валидную ссылку на видео")
        return

    if not is_supported_url(user_message):
        await update.message.reply_text("❌ Ссылка не поддерживается")
        return

    status_msg = await update.message.reply_text("⏳ Скачиваю видео...")

    try:
        file_path = await download_video(user_message)
        
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            caption = f"✅ **Готово!**\n💾 Размер: {file_size:.1f}MB"
            
            await update.message.reply_video(
                video=open(file_path, 'rb'),
                caption=caption,
                supports_streaming=True,
                parse_mode='Markdown'
            )
            await status_msg.delete()
            os.remove(file_path)
        else:
            await status_msg.edit_text("❌ Ошибка скачивания")
            
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        await status_msg.edit_text("❌ Ошибка. Попробуйте другую ссылку")

async def download_video(url: str) -> str:
    os.makedirs(temp_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(temp_dir, '%(title).100s.%(ext)s'),
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logger.error(f"Ошибка скачивания: {str(e)}")
        return None

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    global bot_app
    try:
        if bot_app:
            update = Update.de_json(request.get_json(), bot_app.bot)
            asyncio.run_coroutine_threadsafe(
                bot_app.process_update(update),
                bot_app._get_running_loop()
            )
        return 'ok', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'error', 500

async def setup_webhook():
    """Настройка webhook"""
    global bot_app
    try:
        render_url = os.getenv('RENDER_EXTERNAL_URL')
        if render_url:
            webhook_url = f"{render_url}/webhook"
            await bot_app.bot.set_webhook(webhook_url)
            logger.info(f"Webhook установлен: {webhook_url}")
        else:
            logger.warning("RENDER_EXTERNAL_URL не найден, используем polling")
    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")

def run():
    """Запуск приложения"""
    global bot_app
    
    # Инициализируем бота
    bot_app = init_bot()
    
    if bot_app:
        # Настраиваем webhook
        asyncio.run(setup_webhook())
        
        # Запускаем бота в фоне
        bot_app._get_running_loop()
        logger.info("Бот запущен")
    else:
        logger.error("Не удалось инициализировать бота")

# Запускаем при старте
run()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
