from flask import Flask
import threading
import requests
import time
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!", 200

@app.route('/ping')
def ping():
    return "pong", 200

def run_flask():
    app.run(host='0.0.0.0', port=5000)

def keep_alive():
    """Функция для поддержания активности"""
    def run():
        run_flask()
    
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()

# Авто-пинг для Render
def auto_ping():
    """Автоматически пингует приложение каждые 5 минут"""
    while True:
        try:
            if os.getenv('RENDER_EXTERNAL_URL'):
                requests.get(f"{os.getenv('RENDER_EXTERNAL_URL')}/health")
            time.sleep(300)  # 5 минут
        except:
            pass

# Запускаем авто-пинг в отдельном потоке
ping_thread = threading.Thread(target=auto_ping)
ping_thread.daemon = True
ping_thread.start()
