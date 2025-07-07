import os
from flask import Flask, request, jsonify
import time # For simulating delay
import telebot # You need to install 'pyTelegramBotAPI' for this: pip install pyTelegramBotAPI
from dotenv import load_dotenv # You need to install 'python-dotenv' for this: pip install python-dotenv

app = Flask(__name__)

# --- Load environment variables from .env file ---
load_dotenv()

# --- Telegram Configuration (Get from environment variables) ---
# Dapatkan token bot Telegram dari variabel lingkungan.
# Jika tidak ditemukan, gunakan nilai default atau tampilkan error.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Dapatkan ID chat atau channel tujuan notifikasi dari variabel lingkungan.
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Pastikan token dan chat ID telah dimuat
if not TELEGRAM_BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN tidak ditemukan di variabel lingkungan atau file .env")
    exit(1)
if not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_CHAT_ID tidak ditemukan di variabel lingkungan atau file .env")
    exit(1)

# Inisialisasi bot Telegram
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

@app.route('/send_notification', methods=['POST'])
def send_notification():
    """
    Endpoint untuk mengirim notifikasi ke Telegram.
    Menerima pesan dalam format JSON: {"message": "Pesan Anda di sini"}
    """
    message = request.json.get('message')
    if not message:
        return jsonify({"error": "No message provided"}), 400

    print(f"\n[Telegram Server] Menerima permintaan notifikasi: '{message}'")

    try:
        # Kirim pesan menggunakan bot Telegram
        bot.send_message(TELEGRAM_CHAT_ID, message)
        
        # Simulasi delay pengiriman (opsional, untuk tujuan demo)
        time.sleep(0.5) 
        print(f"[Telegram Server] Notifikasi Telegram berhasil dikirim: '{message}'")
        return jsonify({"status": "Notifikasi Telegram berhasil dikirim."})
    except Exception as e:
        print(f"[Telegram Server] Error saat mengirim notifikasi: {e}")
        # Tangani error spesifik dari API Telegram jika diperlukan
        return jsonify({"status": f"Gagal mengirim notifikasi Telegram: {e}"}), 500

if __name__ == '__main__':
    print("Memulai MCP Server Notification Telegram di http://127.0.0.1:5002")
    print("Pastikan TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID diatur di file .env atau variabel lingkungan sistem.")
    app.run(port=5002, debug=True) # debug=True hanya untuk pengembangan, nonaktifkan di produksi
