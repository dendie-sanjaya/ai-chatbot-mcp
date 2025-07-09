import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
import json
import re # Import modul re untuk ekspresi reguler

# Mengubah import LangChain ke import Google Generative AI nativ
import google.generativeai as genai 

app = Flask(__name__)
CORS(app)

# --- 0. Konfigurasi Lingkungan ---
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in your .env file.")

RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:5001/rag_query")
TELEGRAM_NOTIFICATION_SERVER_URL = os.getenv("TELEGRAM_NOTIFICATION_SERVER_URL", "http://127.00.0.1:5002/send_notification")

# --- 1. Inisialisasi LLM (Gemini) ---
# Menggunakan inisialisasi model Gemini nativ
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash')

# Variabel global untuk menyimpan data RAG yang terakhir diambil
# Ini akan digunakan untuk mengirim ke Telegram jika diminta
rag_data_for_telegram = "" 

# --- 2. Definisi Tools/Services Eksternal (Simulasi MCP Server) ---

def fetch_external_data_from_rag(rag_query: str, rag_tipe: str) -> str:
    """
    Memanggil MCP Server RAG untuk mendapatkan data eksternal dari database.
    rag_query: Nama produk atau istilah pencarian yang relevan untuk database.
    rag_tipe: Tipe informasi yang diminta ('harga', 'stok', 'detail').
    """
    global rag_data_for_telegram # Deklarasikan penggunaan variabel global
    print(f"DEBUG (Backend): Meminta data RAG untuk query: '{rag_query}' dengan tipe: '{rag_tipe}'")
    try:
        response = requests.post(RAG_SERVER_URL, json={"query": rag_query, "tipe": rag_tipe}, timeout=10)
        response.raise_for_status() 
        rag_data = response.json().get("data", "Tidak ada data relevan ditemukan.")
        
        rag_data_for_telegram = rag_data 

        if rag_data == "Tidak ada data relevan ditemukan.":
            print("DEBUG (Backend): Tidak ada data relevan ditemukan di RAG.")
            return rag_data
        
        print(f"DEBUG (Backend): Data RAG yang diterima: {rag_data}")
        return rag_data
    except requests.exceptions.ConnectionError:
        rag_data_for_telegram = "Error: Tidak dapat terhubung ke server RAG." 
        return "Error: Tidak dapat terhubung ke server RAG. Pastikan MCP Server RAG berjalan."
    except requests.exceptions.HTTPError as e:
        rag_data_for_telegram = f"Error HTTP saat mengambil data RAG: {e.response.status_code} - {e.response.text}" 
        return f"Error HTTP saat mengambil data RAG: {e.response.status_code} - {e.response.text}"
    except requests.exceptions.RequestException as e:
        rag_data_for_telegram = f"Error saat mengambil data RAG: {e}" 
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

# --- 3. Definisi Prompt untuk Chatbot (Tidak lagi menggunakan LangChain ChatPromptTemplate) ---
# Instruksi prompt akan dibangun secara langsung di fungsi chat()

# --- 4. Membangun Chain (Tidak lagi menggunakan LangChain Runnables) ---

# Fungsi untuk menentukan dan mengambil konteks RAG berdasarkan heuristik
# Mengembalikan tuple (context_string, rag_tipe_for_rag_server)
def determine_and_fetch_rag_context(input_dict: dict) -> tuple[str, str]:
    """
    Menentukan apakah query RAG diperlukan berdasarkan pertanyaan pengguna,
    mengekstraksi nama produk dan tipe, lalu mengambil data dari server RAG.
    Mengembalikan tuple (context_string, rag_tipe_for_rag_server).
    """
    try: 
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
                product_match = re.match(r"^([\w\s]+?)(?:[\s,.;!?'\"]|$)", remaining_query_after_keyword)
                
                if product_match and product_match.group(1).strip():
                    rag_query_for_rag_server = product_match.group(1).strip()
                else:
                    rag_query_for_rag_server = ""
            else:
                rag_query_for_rag_server = ""
        else:
            product_match_general = re.match(r"^([\w\s]+?)(?:[\s,.;!?'\"]|$)", cleaned_query_lower)
            if product_match_general and product_match_general.group(1).strip():
                rag_query_for_rag_server = product_match_general.group(1).strip()
            else:
                rag_query_for_rag_server = ""

        print(f"DEBUG (Backend): RAG query term: '{rag_query_for_rag_server}', RAG type: '{rag_tipe_for_rag_server}' (dari original '{user_question}')")

        if not rag_query_for_rag_server.strip():
            print(f"DEBUG (Backend): determine_and_fetch_rag_context returning (no RAG query): ('Tidak ada konteks eksternal yang dibutuhkan.', 'general')")
            return "Tidak ada konteks eksternal yang dibutuhkan.", "general"
        
        print(f"DEBUG (Backend): Memanggil server RAG dengan query: '{rag_query_for_rag_server}' dan tipe: '{rag_tipe_for_rag_server}'")
        context_str = fetch_external_data_from_rag(rag_query_for_rag_server, rag_tipe_for_rag_server)
        
        # Safeguard: Ensure context_str is always a string
        if not isinstance(context_str, str):
            print(f"WARNING: fetch_external_data_from_rag returned non-string type: {type(context_str)}. Defaulting to error string.")
            context_str = "Error: Konteks tidak valid dari server RAG."

        print(f"DEBUG (Backend): determine_and_fetch_rag_context returning: ({context_str!r}, {rag_tipe_for_rag_server!r})")
        return context_str, rag_tipe_for_rag_server
    except Exception as e:
        print(f"ERROR (determine_and_fetch_rag_context): An unexpected error occurred: {e}")
        return f"Error internal saat memproses query RAG: {e}", "general"


# Helper function untuk memetakan tipe RAG ke peran LLM
def get_llm_role_from_rag_type(rag_type: str) -> str:
    if rag_type == "harga":
        return "Anda adalah asisten penjualan yang ramah dan informatif untuk produk retail."
    elif rag_type == "stok":
        return "Anda adalah customer service yang ramah dan responsif untuk layanan inventaris produk."
    elif rag_type == "detail":
        return "Anda adalah asisten informasi produk yang ramah dan detail."
    else: # "general" atau tipe non-spesifik lainnya
        return "Anda adalah AI Chatbot yang ramah dan membantu."

# --- CHATBOT CHAIN DIHAPUS ---
# Logika pembuatan prompt dan pemanggilan LLM akan langsung di dalam endpoint /chat

# --- 5. API Endpoint untuk Frontend ---

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    print(f"\n[Backend] Menerima pesan dari Frontend: '{user_message}'")

    try:
        # Langkah 1: Tentukan dan ambil konteks RAG serta tipenya
        rag_context_string, rag_tipe = determine_and_fetch_rag_context(input_dict={"question": user_message})
        
        # Langkah 2: Tentukan peran LLM berdasarkan tipe RAG
        llm_role = get_llm_role_from_rag_type(rag_tipe)

        # Langkah 3: Buat prompt secara nativ seperti yang Anda inginkan
        prompt_parts = [
            llm_role, # Peran LLM
            f"KONTEKS DATABASE:\n{rag_context_string}", # Konteks RAG
            f"PERTANYAAN PENGGUNA:\n{user_message}", # Pertanyaan pengguna
            "INSTRUKSI:\n" # Instruksi untuk menjawab
            "Anda adalah asisten yang ramah, informatif, dan ringkas. "
            "Berdasarkan KONTEKS DATABASE yang diberikan, jawab pertanyaan pengguna secara langsung, ringkas, dan informatif. "
            "Jika KONTEKS DATABASE berisi data yang valid (bukan pesan 'Tidak ada data relevan ditemukan.' atau error), Anda HARUS menggunakan data tersebut sebagai jawaban utama Anda. "
            "Contoh: 'Harga Produk A adalah $1200.00.' atau 'Stok Laptop Gaming X saat ini tersedia 15 unit.' atau 'Detail Produk A: Produk A adalah barang elektronik berkualitas tinggi.' "
            "Jika KONTEKS DATABASE menyatakan 'Tidak ada data relevan ditemukan.' atau berisi pesan error, Anda HARUS menjawab dengan: 'Maaf, saya tidak menemukan informasi tentang produk tersebut di database kami. Apakah ada hal lain yang bisa saya bantu?' "
            "JANGAN PERNAH mengarang informasi produk jika tidak ada di KONTEKS DATABASE. "
            "JANGAN PERNAH menghasilkan placeholder atau teks seperti '{answer}', '{jawaban}', atau sejenisnya. Berikan jawaban yang lengkap dan langsung. "
            "Jika pertanyaan pengguna juga berisi instruksi terkait 'telegram' (misalnya 'kirim ke telegram', 'send telegram', 'kirim notifikasi'), Anda **HARUS mengabaikan instruksi 'telegram' tersebut dalam jawaban utama Anda** dan fokus HANYA pada penyediaan informasi produk berdasarkan KONTEKS DATABASE. Informasi terkait Telegram akan ditangani secara terpisah oleh sistem." 
            "Jika pertanyaan tidak terkait produk atau tidak memerlukan KONTEKS DATABASE, jawablah berdasarkan pengetahuan umum Anda. "
            "Selalu berikan jawaban yang ramah dan membantu."
        ]
        
        full_prompt = "\n\n".join(filter(None, prompt_parts)) # Gabungkan semua bagian prompt

        print(f"DEBUG (Backend): Full prompt yang dikirim ke Gemini:\n{full_prompt}")

        # Langkah 4: Panggil Gemini API secara nativ
        gemini_response = gemini_model.generate_content(full_prompt)
        chatbot_response = gemini_response.text # Ambil teks dari respons Gemini

        # Periksa apakah pesan pengguna mengandung kata kunci untuk mengirim ke Telegram
        if any(keyword in user_message.lower() for keyword in ["kirim telegram", "send telegram", "segeranotif", "telegram", "kirim notifikasi", "kirim ke"]):
            if rag_data_for_telegram and rag_data_for_telegram != "Tidak ada data relevan ditemukan.":
                notification_message = f"Data RAG yang diminta: {rag_data_for_telegram}"
                notification_status = send_telegram_notification(notification_message)
                final_response = f"{chatbot_response} <br /><br />Status Notifikasi Telegram: {notification_status}"
            else:
                final_response = f"{chatbot_response} <br /><br />Tidak ada data RAG yang relevan untuk dikirim ke Telegram atau terjadi error saat mengambil data."
        else:
            final_response = chatbot_response

        return jsonify({"response": final_response})

    except Exception as e:
        print(f"[Backend] Error saat memproses pesan: {e}")
        return jsonify({"error": f"Maaf, terjadi kesalahan internal pada chatbot: {e}"}), 500

if __name__ == '__main__':
    print("Memulai App Backend Chatbot (Langchain Framework) di http://127.0.0.1:5000")
    print("Pastikan MCP Server RAG (port 5001) dan MCP Server Telegram (port 5002) berjalan.")
    app.run(port=5000, debug=True)
