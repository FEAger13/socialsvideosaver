from app import flask_app, bot_instance
import asyncio
import os

async def setup_bot():
    """Настройка бота при запуске"""
    await bot_instance.setup_webhook()

# Настраиваем webhook при импорте
if os.environ.get('RENDER'):
    asyncio.run(setup_bot())

if __name__ == "__main__":
    flask_app.run()
