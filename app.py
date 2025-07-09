import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import json
import re # Import modul re untuk ekspresi reguler

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
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3, google_api_key=GEMINI_API_KEY)

# Variabel global untuk menyimpan data RAG yang terakhir diambil
# Ini akan digunakan untuk mengirim ke Telegram jika diminta
rag_data_for_telegram = "" 

# --- 2. Definisi Tools/Services Eksternal (Simulasi MCP Server) ---

# Fungsi ini sekarang menerima 'rag_query' (nama produk/istilah pencarian) dan 'rag_tipe' (harga/stok/detail)
def fetch_external_data_from_rag(rag_query: str, rag_tipe: str) -> str:
    """
    Memanggil MCP Server RAG untuk mendapatkan data eksternal dari database.
    rag_query: Nama produk atau istilah pencarian yang relevan untuk database.
    rag_tipe: Tipe informasi yang diminta ('harga', 'stok', 'detail').
    """
    global rag_data_for_telegram # Deklarasikan penggunaan variabel global
    print(f"DEBUG (Backend): Meminta data RAG untuk query: '{rag_query}' dengan tipe: '{rag_tipe}'")
    try:
        # Mengirim kedua parameter 'query' dan 'tipe' dalam body JSON
        response = requests.post(RAG_SERVER_URL, json={"query": rag_query, "tipe": rag_tipe}, timeout=10)
        response.raise_for_status() # Akan memicu HTTPError untuk respons 4xx/5xx
        rag_data = response.json().get("data", "Tidak ada data relevan ditemukan.")
        
        # Simpan data RAG ke variabel global
        rag_data_for_telegram = rag_data 

        if rag_data == "Tidak ada data relevan ditemukan.":
            print("DEBUG (Backend): Tidak ada data relevan ditemukan di RAG.")
            return rag_data
        
        print(f"DEBUG (Backend): Data RAG yang diterima: {rag_data}")
        return rag_data
    except requests.exceptions.ConnectionError:
        rag_data_for_telegram = "Error: Tidak dapat terhubung ke server RAG." # Simpan pesan error juga
        return "Error: Tidak dapat terhubung ke server RAG. Pastikan MCP Server RAG berjalan."
    except requests.exceptions.HTTPError as e:
        rag_data_for_telegram = f"Error HTTP saat mengambil data RAG: {e.response.status_code} - {e.response.text}" # Simpan pesan error juga
        return f"Error HTTP saat mengambil data RAG: {e.response.status_code} - {e.response.text}"
    except requests.exceptions.RequestException as e:
        rag_data_for_telegram = f"Error saat mengambil data RAG: {e}" # Simpan pesan error juga
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

# --- 3. Definisi Prompt untuk Chatbot ---
CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            "Anda adalah AI Chatbot yang membantu dan informatif, bertindak sebagai customer service untuk online shop. "
            "Tugas utama Anda adalah memberikan informasi yang akurat dan responsif. "
            "**SANGAT PENTING:** Anda **harus selalu** menggunakan informasi yang diberikan dalam CONTEXT untuk menjawab pertanyaan pengguna terkait produk. "
            "Contoh: Jika CONTEXT adalah 'Stok Laptop Gaming X saat ini tersedia 15 unit.', maka respons Anda harus seperti 'Stok Laptop Gaming X saat ini tersedia 15 unit.' atau 'Tentu, stok Laptop Gaming X yang tersedia adalah 15 unit.' "
            "Jika CONTEXT adalah 'Detail Produk A: Produk A adalah barang elektronik berkualitas tinggi.', maka respons Anda harus seperti 'Produk A adalah barang elektronik berkualitas tinggi.' atau 'Tentu, detail Produk A adalah: Produk A adalah barang elektronik berkualitas tinggi.' "
            "Jangan pernah mengarang informasi produk jika tidak ada di CONTEXT. "
            "**JANGAN PERNAH menghasilkan placeholder atau teks seperti '{answare}' atau sejenisnya.** "
            "Jika CONTEXT menyatakan 'Tidak ada data relevan ditemukan.' atau berisi pesan error, informasikan kepada pengguna bahwa informasi tersebut tidak tersedia di database dan tawarkan bantuan lain. "
            "Jika pertanyaan tidak memerlukan CONTEXT atau CONTEXT tidak relevan, jawablah berdasarkan pengetahuan umum Anda. "
            "Selalu berikan jawaban yang ramah dan membantu."
            "\n\n--- CONTEXT START ---\n{context}\n--- CONTEXT END ---\n"
        ),
        HumanMessage(content="{question}"),
    ]
)

# --- 4. Membangun LangChain ---
# Fungsi untuk menentukan dan mengambil konteks RAG berdasarkan heuristik
# Fungsi untuk menentukan dan mengambil konteks RAG berdasarkan heuristik
def determine_and_fetch_rag_context(input_dict: dict) -> str:
    """
    Menentukan apakah query RAG diperlukan berdasarkan pertanyaan pengguna,
    mengekstraksi nama produk dan tipe, lalu mengambil data dari server RAG.
    """
    user_question = input_dict["question"]
    query_lower = user_question.lower()

    # Kata kunci untuk notifikasi Telegram
    telegram_keywords = ["kirim telegram", "send telegram", "segeranotif", "telegram", "kirim notifikasi", "kirim ke"] 

    # Hapus kata kunci Telegram dari pertanyaan agar tidak mengganggu ekstraksi RAG
    cleaned_query_lower = query_lower
    for keyword in telegram_keywords:
        cleaned_query_lower = re.sub(r'\b' + re.escape(keyword) + r'\b', ' ', cleaned_query_lower).strip()
    cleaned_query_lower = ' '.join(cleaned_query_lower.split()) # Hapus spasi ganda

    # Nilai default untuk parameter server RAG
    rag_query_for_rag_server = "" # Ini akan menjadi nama produk yang diekstrak
    rag_tipe_for_rag_server = "detail" # Tipe default jika tidak ada kata kunci spesifik yang cocok

    # Pembatas nama produk dalam kueri
    # Karakter ' (single quote) juga ditambahkan untuk penanganan yang lebih baik
    product_name_delimiters = r"\b(?:dan|untuk|dengan|tentang|yang|di|pada|dari|ke|,|.|\?|'|$)\b" 

    # Kata kunci utama RAG dan tipe yang sesuai
    primary_rag_keywords = {
        "berapa sisa": "stok",
        "berapa harga": "harga",
        "harga": "harga",
        "stok": "stok",
        "jelaskan": "detail",
        "apa itu": "detail",
        "detail": "detail",
        "nama produk": "detail", # Jika "nama produk" ditanyakan, biasanya untuk detail umum
    }

    found_keyword_phrase = ""
    
    # Cari kata kunci RAG yang paling spesifik terlebih dahulu
    for phrase, base_term in sorted(primary_rag_keywords.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(r'\b' + re.escape(phrase) + r'\b', cleaned_query_lower):
            rag_tipe_for_rag_server = base_term
            found_keyword_phrase = phrase
            break

    if found_keyword_phrase:
        keyword_match_obj = re.search(r'\b' + re.escape(found_keyword_phrase) + r'\b', cleaned_query_lower)
        
        if keyword_match_obj:
            remaining_query_after_keyword = cleaned_query_lower[keyword_match_obj.end():].strip()
            
            # Regex untuk mengekstrak nama produk:
            # - ^([\w\s]+?) : Tangkap karakter kata dan spasi secara non-greedy dari awal string
            # - (?:[\s,.;!?'\"]|$) : Hentikan penangkapan jika bertemu spasi, koma, titik, dll., atau akhir string
            # Perbaikan: Meng-escape double quote (") di dalam character class
            product_match = re.match(r"^([\w\s]+?)(?:[\s,.;!?'\"]|$)", remaining_query_after_keyword)
            
            if product_match and product_match.group(1).strip():
                rag_query_for_rag_server = product_match.group(1).strip()
            else:
                # Jika tidak ada nama produk spesifik yang ditemukan setelah kata kunci,
                # set rag_query_for_rag_server menjadi kosong.
                rag_query_for_rag_server = ""
        else:
            # Fallback jika kata kunci tidak ditemukan lagi (seharusnya tidak terjadi)
            rag_query_for_rag_server = "" # Set to empty if keyword match fails unexpectedly
    else:
        # Jika tidak ada kata kunci RAG spesifik ditemukan, coba ekstrak nama produk dari seluruh kueri yang sudah dibersihkan
        # Ini adalah kasus di mana user hanya mengetik "Produk A" tanpa kata kunci seperti "harga" atau "stok"
        product_match_general = re.match(r"^([\w\s]+?)(?:[\s,.;!?'\"]|$)", cleaned_query_lower)
        if product_match_general and product_match_general.group(1).strip():
            rag_query_for_rag_server = product_match_general.group(1).strip()
        else:
            rag_query_for_rag_server = "" # Tidak ada nama produk yang teridentifikasi

    print(f"DEBUG (Backend): RAG query term: '{rag_query_for_rag_server}', RAG type: '{rag_tipe_for_rag_server}' (dari original '{user_question}')")

    if not rag_query_for_rag_server.strip():
        return "Tidak ada konteks eksternal yang dibutuhkan."
    
    # Panggil server RAG dengan kueri dan tipe yang ditentukan
    print(f"DEBUG (Backend): Memanggil server RAG dengan query: '{rag_query_for_rag_server}' dan tipe: '{rag_tipe_for_rag_server}'")
    return fetch_external_data_from_rag(rag_query_for_rag_server, rag_tipe_for_rag_server)

# Fungsi ini sekarang akan mengembalikan string yang berisi data RAG atau pesan error
# Jika tidak ada data yang ditemukan, akan mengembalikan "Tidak ada konteks eksternal yang dibutuhkan." 
# chatbot_chain sekarang hanya memiliki satu panggilan LLM
chatbot_chain = (
    {
        "question": RunnablePassthrough(),
        # Konteks RAG sekarang ditentukan dan diambil oleh fungsi Python
        "context": RunnableLambda(determine_and_fetch_rag_context),
    }
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
        # Panggil chatbot_chain dengan input dictionary yang benar
        # Ini akan menjalankan determine_and_fetch_rag_context secara internal
        # dan mengisi 'context' untuk CHAT_PROMPT.
        #chatbot_response = chatbot_chain.invoke({"question": user_message}) # PERBAIKAN UTAMA DI SINI

        chatbot_response = determine_and_fetch_rag_context({"question": user_message})

        # Periksa apakah pesan pengguna mengandung kata kunci untuk mengirim ke Telegram
        if any(keyword in user_message.lower() for keyword in ["kirim telegram", "send telegram", "segeranotif", "telegram", "kirim notifikasi", "kirim ke"]):
            if rag_data_for_telegram and rag_data_for_telegram != "Tidak ada data relevan ditemukan.":
                notification_message = f"Data RAG yang diminta: {rag_data_for_telegram}"
                notification_status = send_telegram_notification(notification_message)
                # Tambahkan status notifikasi ke respons chatbot
                final_response = f"{chatbot_response} <br /><br />Status Notifikasi Telegram: {notification_status}"
            else:
                final_response = f"{chatbot_response} <br /><br />Tidak ada data RAG yang relevan untuk dikirim ke Telegram atau terjadi error saat mengambil data."
        else:
            final_response = chatbot_response

        # Mengirim respons sebagai JSON
        return jsonify({"response": final_response})

    except Exception as e:
        print(f"[Backend] Error saat memproses pesan: {e}")
        return jsonify({"error": f"Maaf, terjadi kesalahan internal pada chatbot: {e}"}), 500

if __name__ == '__main__':
    print("Memulai App Backend Chatbot (Langchain Framework) di http://127.0.0.1:5000")
    print("Pastikan MCP Server RAG (port 5001) dan MCP Server Telegram (port 5002) berjalan.")
    app.run(port=5000, debug=True)
