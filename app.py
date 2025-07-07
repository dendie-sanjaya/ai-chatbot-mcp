import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import json

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate 
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.schema.runnable import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

app = Flask(__name__)
CORS(app)

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
    Memanggil MCP Server RAG untuk mendapatkan data eksternal dari database.
    """
    print(f"DEBUG (Backend): Meminta data RAG untuk query: '{query}'")
    try:
        response = requests.post(RAG_SERVER_URL, json={"query": query}, timeout=10)
        response.raise_for_status()
        rag_data = response.json().get("data", "Tidak ada data relevan ditemukan.")
        print(f"DEBUG (Backend): Data RAG yang diterima: {rag_data}")
        return rag_data
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
        response = requests.post(TELEGRAM_NOTIFICATION_SERVER_URL, json={"message": message}, timeout=10)
        response.raise_for_status()
        return response.json().get("status", "Notifikasi berhasil dikirim.")
    except requests.exceptions.ConnectionError:
        return "Error: Tidak dapat terhubung ke server notifikasi Telegram."
    except requests.exceptions.RequestException as e:
        return f"Error saat mengirim notifikasi Telegram: {e}"

# --- 3. Prompt Engineering ---

RAG_QUERY_GENERATOR_PROMPT = PromptTemplate.from_template(
    """Berdasarkan pertanyaan pengguna berikut, identifikasi kata kunci atau frasa yang **secara spesifik** berkaitan dengan pencarian 'nama produk', 'detail stok', atau 'harga' untuk mencari informasi tambahan di database eksternal. Jika pertanyaan tidak secara langsung meminta informasi tersebut (nama produk, detail stok, atau harga), balas dengan "NONE".

    Contoh:
    Pertanyaan: Berapa harga produk A?
    Output: harga produk A

    Pertanyaan: Berapa stok produk A?
    Output: detail stok produk A

    Pertanyaan: Apa nama produk X?
    Output: nama produk X

    Pertanyaan: Jelaskan produk A?
    Output: detail produk A   
    
    Pertanyaan: {question}
    Output: """
)

CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            "Anda adalah AI Chatbot yang membantu dan informatif, bertindak sebagai customer service untuk online shop. "
            "Tugas utama Anda adalah memberikan informasi yang akurat dan responsif. "
            "Selalu berikan jawaban yang ramah dan membantu."
            "\n\n--- CONTEXT START ---\n{context}\n--- CONTEXT END ---\n" # Menambahkan delimiter di sini
        ),
        HumanMessage(content="{question}"),
    ]
)

# --- 4. Membangun LangChain ---

rag_query_chain = RAG_QUERY_GENERATOR_PROMPT | llm | StrOutputParser()

def get_rag_context(query: str) -> str:
    print(f"DEBUG (Backend): rag_query_chain menghasilkan: '{query}'")
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

    def generate():
        try:
            for chunk in chatbot_chain.stream({"question": user_message}):
                yield json.dumps({"response_chunk": chunk}) + '\n'

            if "urgent" in user_message.lower() or "penting" in user_message.lower():
                notification_status = send_telegram_notification(f"Pesan penting dari chatbot: {user_message}")
                yield json.dumps({"notification_status": notification_status}) + '\n'

        except Exception as e:
            print(f"[Backend] Error saat memproses pesan: {e}")
            yield json.dumps({"error": f"Maaf, terjadi kesalahan internal pada chatbot: {e}"}) + '\n'

    return Response(stream_with_context(generate()), mimetype='application/json')

if __name__ == '__main__':
    print("Memulai App Backend Chatbot (Langchain Framework) di http://127.0.0.1:5000")
    print("Pastikan MCP Server RAG (port 5001) dan MCP Server Telegram (port 5002) berjalan.")
    app.run(port=5000, debug=True)
