from flask import Flask, request, jsonify
import time # Untuk simulasi delay database
import random # Untuk simulasi data acak

app = Flask(__name__)

# --- Simulasi Database MySQL ---
# Dalam implementasi nyata, ini akan menjadi koneksi ke database MySQL Anda
DATABASE_SIMULATION = {
    "harga produk a": "Harga produk A adalah $1200.",
    "spesifikasi laptop gaming": "Laptop Gaming X memiliki RAM 16GB, SSD 512GB, dan RTX 3060.",
    "cuaca bandung": "Cuaca di Bandung saat ini 24°C dan berawan.",
    "jam operasional toko": "Toko buka dari jam 09:00 - 20:00 setiap hari kerja."
}

@app.route('/rag_query', methods=['POST'])
def rag_query():
    query = request.json.get('query')
    if not query:
        return jsonify({"error": "No query provided"}), 400

    print(f"\n[RAG Server] Menerima query RAG: '{query}'")

    # Simulasi delay query ke database
    time.sleep(random.uniform(0.5, 1.5))

    # Simulasi pencarian di database
    # Dalam nyata, Anda akan melakukan pencarian SQL atau pencarian vektor di sini
    found_data = "Tidak ada data relevan dari MySQL."
    for key, value in DATABASE_SIMULATION.items():
        if key in query.lower():
            found_data = value
            break
    
    print(f"[RAG Server] Mengembalikan data: '{found_data}'")
    return jsonify({"data": found_data})

if __name__ == '__main__':
    print("Memulai MCP Server RAG di http://127.0.0.1:5001")
    app.run(port=5001, debug=True) # debug=True hanya untuk pengembangan