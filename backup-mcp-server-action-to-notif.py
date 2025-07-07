from dotenv import load_dotenv
import os
# from langchain_openai import ChatOpenAI # Hapus atau komen baris ini
from langchain_google_genai import ChatGoogleGenerativeAI # Import untuk Gemini
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
import datetime

load_dotenv() # Memuat variabel lingkungan dari file .env

# --- 1. Inisialisasi LLM (Sekarang Menggunakan Gemini) ---
# Pastikan GOOGLE_API_KEY sudah diatur di .env
llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.5)

# --- 2. Definisi Tools (Alat) yang Dapat Dipanggil Agen ---
# Tools ini sama persis seperti sebelumnya karena mereka tidak bergantung pada LLM-nya
@tool
def send_notification(recipient: str, message: str) -> str:
    """
    Mengirim notifikasi ke penerima tertentu dengan pesan yang diberikan.
    Contoh: send_notification(recipient='08123456789', message='Halo, ini notifikasi dari AI.')
    """
    print(f"\n--- Mengirim Notifikasi ---")
    print(f"Penerima: {recipient}")
    print(f"Pesan   : {message}")
    print(f"Status  : Notifikasi berhasil dikirim (simulasi).\n")
    return f"Notifikasi ke {recipient} dengan pesan '{message}' telah berhasil dikirim."

@tool
def toggle_light(state: str, location: str = "ruang tamu") -> str:
    """
    Mengubah status lampu (ON atau OFF) di lokasi tertentu.
    'state' harus 'ON' atau 'OFF'. Lokasi default adalah 'ruang tamu'.
    Contoh: toggle_light(state='ON', location='dapur')
    """
    state_lower = state.lower()
    if state_lower not in ["on", "off"]:
        return "Gagal: Status lampu harus 'ON' atau 'OFF'."

    print(f"\n--- Mengontrol Lampu ---")
    print(f"Perintah: Menyalakan/Mematikan lampu di {location}")
    print(f"Status  : Lampu di {location} sekarang {state.upper()} (simulasi via API Smart Home).\n")
    return f"Lampu di {location} berhasil diatur ke {state.upper()}."

@tool
def get_current_time() -> str:
    """
    Mengambil waktu dan tanggal saat ini.
    """
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n--- Mengambil Waktu Saat Ini ---")
    print(f"Waktu saat ini: {current_time}\n")
    return f"Waktu saat ini adalah {current_time} WIB."


# --- 3. Kumpulkan Semua Tools ---
tools = [send_notification, toggle_light, get_current_time]

# --- 4. Definisi Prompt untuk Agen (Sama) ---
# Prompt ini akan menginstruksikan LLM bagaimana berpikir dan menggunakan alat.
# Menggunakan format ReAct (Thought, Action, Action Input, Observation)
template = """Jawab pertanyaan pengguna sebisa mungkin. Anda memiliki akses ke alat berikut:

{tools}

Gunakan format berikut:

Question: Pertanyaan input yang harus Anda jawab
Thought: Anda harus selalu memikirkan apa yang harus dilakukan
Action: Aksi yang harus diambil, harus salah satu dari [{tool_names}]
Action Input: Input untuk aksi tersebut (misalnya, nama kota)
Observation: Hasil dari aksi
... (ini Thought/Action/Action Input/Observation bisa berulang beberapa kali)
Thought: Saya tahu jawaban terakhir
Final Answer: Jawaban akhir untuk pertanyaan asli

Mulai!

Question: {input}
Thought:{agent_scratchpad}"""

prompt = PromptTemplate.from_template(template)


# --- 5. Buat Agen dan Executor (Sama) ---
# create_react_agent adalah fungsi yang direkomendasikan untuk agen ReAct
agent = create_react_agent(llm, tools, prompt)

# AgentExecutor yang menjalankan agen, alat, dan prompt
# verbose=True sangat membantu untuk melihat proses pemikiran agen
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)

# --- 6. Uji Interaksi (Sama) ---

print("--- Contoh 1: Mengirim Notifikasi ---")
user_query_1 = "Tolong kirim pesan ke 08123456789 dengan isi 'Meeting dimulai dalam 10 menit!'"
agent_executor.invoke({"input": user_query_1})

print("\n" + "="*50 + "\n")

print("--- Contoh 2: Menyalakan Lampu ---")
user_query_2 = "Nyalakan lampu di ruang tamu."
agent_executor.invoke({"input": user_query_2})

print("\n" + "="*50 + "\n")

print("--- Contoh 3: Mematikan Lampu Dapur ---")
user_query_3 = "Matikan lampu di dapur."
agent_executor.invoke({"input": user_query_3})

print("\n" + "="*50 + "\n")

print("--- Contoh 4: Menanyakan Waktu dan Pertanyaan Umum ---")
user_query_4 = "Hai, jam berapa sekarang? Dan siapa presiden Indonesia?"
agent_executor.invoke({"input": user_query_4})

print("\n" + "="*50 + "\n")

print("--- Contoh 5: Perintah Tidak Jelas ---")
user_query_5 = "Matikan saja." # Tidak jelas apa yang dimatikan
agent_executor.invoke({"input": user_query_5})