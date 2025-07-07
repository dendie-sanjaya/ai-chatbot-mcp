import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS # Untuk mengizinkan permintaan dari frontend
import requests

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI
# Perbaikan: Impor ChatPromptTemplate di sini
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate 
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.schema.runnable import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

app = Flask(__name__)
CORS(app) # Aktifkan CORS untuk mengizinkan frontend di domain lain mengakses API ini

# --- 0. Konfigurasi Lingkungan ---
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in your .env file.")

RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:5001/rag_query")
TELEGRAM_NOTIFICATION_SERVER_URL = os.getenv("TELEGRAM_NOTIFICATION_SERVER_URL", "http://127.0.0.1:5002/send_notification")

# --- 1. Inisialisasi LLM (Gemini) ---
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7, google_api_key=GEMINI_API_KEY)

# --- 2. Definisi Tools/Services Eksternal (Simulasi MCP Server) ---

def fetch_external_data_from_rag(query: str) -> str:
    """
    Memanggil MCP Server RAG untuk mendapatkan data eksternal dari MySQL.
    """
    print(f"DEBUG (Backend): Meminta data RAG untuk query: '{query}'")
    try:
        response = requests.post(RAG_SERVER_URL, json={"query": query}, timeout=10) # Tambah timeout
        response.raise_for_status()
        return response.json().get("data", "Tidak ada data relevan ditemukan.")
    except requests.exceptions.ConnectionError:
        return "Error: Tidak dapat terhubung ke server RAG. Pastikan MCP Server RAG berjalan."
    except requests.exceptions.RequestException as e:
        return f"Error saat mengambil data RAG: {e}"

def send_telegram_notification(message: str) -> str:
    """
    Memanggil MCP Server Notification Telegram untuk mengirim notifikasi.
    """
    print(f"DEBUG (Backend): Mengirim notifikasi Telegram: '{message}'")
    try:
        response = requests.post(TELEGRAM_NOTIFICATION_SERVER_URL, json={"message": message}, timeout=10) # Tambah timeout
        response.raise_for_status()
        return response.json().get("status", "Notifikasi berhasil dikirim.")
    except requests.exceptions.ConnectionError:
        return "Error: Tidak dapat terhubung ke server notifikasi Telegram."
    except requests.exceptions.RequestException as e:
        return f"Error saat mengirim notifikasi Telegram: {e}"

# --- 3. Prompt Engineering ---

RAG_QUERY_GENERATOR_PROMPT = PromptTemplate.from_template(
"""Berdasarkan pertanyaan pengguna berikut, identifikasi kata kunci atau frasa yang relevan untuk mencari informasi tambahan di database eksternal. Jika tidak ada kebutuhan untuk mencari data eksternal, balas dengan "NONE".

Contoh:
Pertanyaan: Berapa harga produk A?
Output: harga produk A

Pertanyaan: Berapa stok produk A?
Output: harga produk A

Pertanyaan: jelaskanproduk A?
Output: harga produk A

"""
)


# Perbaikan: Gunakan ChatPromptTemplate.from_messages
CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            "Anda adalah AI Chatbot yang membantu dan informatif. "
            "Anda adalah seperti customer service yang sangat responsif dan informatif sebuah online shop "
            "Gunakan informasi dari CONTEXT jika relevan untuk menjawab pertanyaan. "
            "Jika tidak ada CONTEXT yang relevan atau tidak cukup informasi, jawablah berdasarkan pengetahuan Anda."
            "\n\nCONTEXT:\n{context}\n"
        ),
        HumanMessage(content="{question}"),
    ]
)

# --- 4. Membangun LangChain ---

rag_query_chain = RAG_QUERY_GENERATOR_PROMPT | llm | StrOutputParser()

def get_rag_context(query: str) -> str:
    if query.strip().lower() == "none":
        return "Tidak ada konteks eksternal yang dibutuhkan."
    return fetch_external_data_from_rag(query)

chatbot_chain = (
    {
        "question": RunnablePassthrough(),
        "rag_query": rag_query_chain,
    }
    | RunnableLambda(lambda x: {
        "question": x["question"],
        "context": get_rag_context(x["rag_query"]),
    })
    | CHAT_PROMPT
    | llm
    | StrOutputParser()
)

# --- 5. API Endpoint untuk Frontend ---

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    print(f"\n[Backend] Menerima pesan dari Frontend: '{user_message}'")

    try:
        # Panggil rantai chatbot LangChain
        response_text = chatbot_chain.invoke({"question": user_message})
        print(f"[Backend] Respons Chatbot: {response_text}")

        # Contoh: Memicu notifikasi Telegram berdasarkan kondisi tertentu
        if "urgent" in user_message.lower() or "penting" in user_message.lower():
            notification_status = send_telegram_notification(f"Pesan penting dari chatbot: {user_message}")
            print(f"[Backend] Notifikasi Telegram Status: {notification_status}")

        return jsonify({"response": response_text})

    except Exception as e:
        print(f"[Backend] Error saat memproses pesan: {e}")
        return jsonify({"response": "Maaf, terjadi kesalahan internal pada chatbot."}), 500

if __name__ == '__main__':
    print("Memulai App Backend Chat Boc (Langchain Framework) di http://127.0.0.1:5000")
    print("Pastikan MCP Server RAG (port 5001) dan MCP Server Telegram (port 5002) berjalan.")
    app.run(port=5000, debug=True) # debug=True hanya untuk pengembangan
