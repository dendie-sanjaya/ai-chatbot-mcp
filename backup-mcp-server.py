from dotenv import load_dotenv
import os
# Ganti import dari langchain_openai menjadi langchain_google_genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate

load_dotenv()

# Pastikan GOOGLE_API_KEY sudah diatur di environment variables
# Jika belum, Anda bisa mengaturnya di sini (TIDAK DISARANKAN untuk produksi):
# os.environ["GOOGLE_API_KEY"] = "YOUR_API_KEY_HERE"
# Dapatkan GOOGLE_API_KEY dari environment variable
google_api_key = os.getenv("GEMINI_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")

# Ubah inisialisasi LLM menjadi Gemini Pro
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7, google_api_key=google_api_key)

# --- 1. Definisi Tools (Alat) ---
# Ini mensimulasikan alat eksternal yang bisa dipanggil LLM

@tool
def get_current_weather(location: str) -> str:
    """Mendapatkan cuaca saat ini untuk sebuah kota."""
    if "jakarta" in location.lower():
        return "Cuaca di Jakarta: Cerah, 30°C."
    elif "bandung" in location.lower():
        return "Cuaca di Bandung: Mendung, 24°C, kemungkinan hujan."
    else:
        return "Maaf, data cuaca untuk lokasi tersebut tidak tersedia."

@tool
def calculate_sum(a: int, b: int) -> int:
    """Menghitung penjumlahan dua angka."""
    return a + b

tools = [get_current_weather, calculate_sum] # Daftarkan semua tool yang tersedia

# --- 2. Prompt untuk Agen ---
# Prompt ini akan menginstruksikan LLM bagaimana berperilaku sebagai agen
# Menggunakan prompt yang disediakan oleh LangChain sangat disarankan untuk agen ReAct
from langchain.prompts import PromptTemplate

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


# --- 3. Buat Agen ---
# create_react_agent adalah fungsi yang direkomendasikan
agent = create_react_agent(llm, tools, prompt)



# --- 4. Buat Agent Executor ---
# Executor yang menjalankan agen, alat, dan prompt
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True) # verbose=True untuk melihat langkah agen




print("\n--- Agen Cuaca ---")
agent_executor.invoke({"input": "Bagaimana cuaca di Jakarta?"})

#print("\n--- Agen Penjumlahan ---")
#agent_executor.invoke({"input": "Berapa 123 ditambah 456?"})

print("\n--- Agen Pertanyaan Umum ---")
agent_executor.invoke({"input": "Siapa presiden Indonesia saat ini?"})