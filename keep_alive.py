# keep_alive.py
from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "Fredly News Bot is ALIVE! (Render 24/7)", 200

@app.route('/health')
def health():
    return 'OK', 200

def run():
    # 强制使用 Render 提供的 PORT，**去掉 8080！**
    port = int(os.environ["PORT"])  # 不能用 get(..., 8080)
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
