# Import library yang diperlukan
import os # Import os untuk menghapus file database jika diperlukan
from flask import Flask, request, jsonify
import time # Untuk simulasi delay database
import random # Untuk simulasi data acak
import sqlite3 # Import library SQLite

app = Flask(__name__)

# Nama file database SQLite
DATABASE_FILE = 'rag_data.db'

def init_db():
    """
    Menginisialisasi database SQLite dan mengisi data sampel.
    Jika file database sudah ada, ia akan dihapus untuk memastikan skema terbaru.
    """
    # Hapus file database jika sudah ada untuk memastikan skema terbaru
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
        print(f"File database '{DATABASE_FILE}' yang sudah ada telah dihapus.")

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Buat tabel jika belum ada
    # Menambahkan kolom 'product_code'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_code TEXT UNIQUE NOT NULL, -- Kolom baru: kode produk
            name TEXT NOT NULL,
            price REAL,
            stock INTEGER,
            description TEXT
        )
    ''')

    # Data sampel produk (menambahkan kode produk)
    products_data = [
        ('PROD001', 'Produk A', 1200.00, 50, 'Produk A adalah barang elektronik berkualitas tinggi.'),
        ('LAPTOPX', 'Laptop Gaming X', 15000.00, 15, 'Laptop Gaming X memiliki RAM 16GB, SSD 512GB, dan RTX 3060.'),
        ('SMARTZ', 'Smartphone Z', 800.00, 120, 'Smartphone Z dilengkapi kamera 108MP dan baterai tahan lama.'),
        ('HPWPRO', 'Headphone Wireless Pro', 250.00, 75, 'Headphone Wireless Pro menawarkan kualitas suara superior dan noise cancellation.')
    ]

    # Masukkan data sampel (hanya jika tabel kosong)
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO products (product_code, name, price, stock, description) VALUES (?, ?, ?, ?, ?)", products_data)
        print("Data produk sampel berhasil diimpor.")
    else:
        print("Tabel 'products' sudah berisi data (ini seharusnya tidak terjadi setelah penghapusan database).")

    conn.commit()

    # --- Tampilkan Data Sampel Setelah Inisialisasi ---
    print("\n--- Data Produk yang Tersedia ---")
    cursor.execute("SELECT id, product_code, name, price, stock, description FROM products")
    products = cursor.fetchall()
    if products:
        for p_id, product_code, name, price, stock, description in products:
            print(f"ID: {p_id}, Kode Produk: {product_code}, Nama: {name}, Harga: ${price:.2f}, Stok: {stock}, Deskripsi: {description}")
    else:
        print("Tidak ada data produk.")
    # --- Akhir Bagian Tampilkan Data Sampel ---

    conn.close()

@app.route('/rag_query', methods=['POST'])
def rag_query():
    query = request.json.get('query')
    if not query:
        return jsonify({"error": "No query provided"}), 400

    print(f"\n[RAG Server] Menerima query RAG: '{query}'")

    # Simulasi delay query ke database
    time.sleep(random.uniform(0.1, 0.5))

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    found_data = "Tidak ada data relevan dari database."

    query_lower = query.lower()
    print(f"[RAG Server] query_lower (setelah di-lowercase): '{query_lower}'") # Debug print

    # Fungsi pembantu untuk mengekstrak nama produk dari kueri yang lebih kompleks
    def extract_product_name(q_lower_local): 
        # Kata kunci yang mungkin mendahului nama produk
        # Urutkan dari frasa terpanjang ke terpendek untuk menghindari pencocokan parsial yang salah
        leading_phrases = [
            "berapa sisa", "detail stok", "nama produk", "apa itu", "jelaskan",
            "harga", "stok", "detail"
        ]
        
        extracted_name = q_lower_local
        for phrase in leading_phrases:
            # Pastikan frasa diikuti oleh spasi untuk menghindari pencocokan parsial kata
            if extracted_name.startswith(phrase + " "): 
                extracted_name = extracted_name[len(phrase) + 1:].strip()
                break # Hentikan setelah menemukan dan menghapus frasa yang cocok pertama
        
        # Jika setelah menghapus frasa, string dimulai dengan "produk" dan bukan bagian dari nama produk sebenarnya
        # Ini adalah bagian yang rumit. Untuk saat ini, kita biarkan saja jika "produk" adalah bagian dari nama.
        # Misalnya, jika produknya adalah "Produk A", kita tidak ingin menghapus "produk".
        # Asumsi: LLM sudah cukup cerdas untuk mengirimkan nama produk yang bersih setelah kata kunci.
        
        return extracted_name

    # Ekstrak nama produk yang mungkin dari kueri yang diterima
    product_search_term = extract_product_name(query_lower)
    print(f"[RAG Server] product_search_term (hasil ekstraksi): '{product_search_term}'") # Debug print

    # Pencarian untuk harga
    if "harga" in query_lower:
        print("[RAG Server] Masuk ke blok 'harga'") # Debug print
        cursor.execute("SELECT name, price FROM products WHERE LOWER(name) LIKE ? OR LOWER(product_code) LIKE ?", ('%' + product_search_term + '%', '%' + product_search_term + '%',))
        result = cursor.fetchone()
        if result:
            found_data = f"Harga {result[0]} adalah ${result[1]:.2f}."
    
    # Pencarian untuk stok
    elif "stok" in query_lower or "berapa sisa" in query_lower:
        print("[RAG Server] Masuk ke blok 'stok'") # Debug print
        cursor.execute("SELECT name, stock FROM products WHERE LOWER(name) LIKE ? OR LOWER(product_code) LIKE ?", ('%' + product_search_term + '%', '%' + product_search_term + '%',))
        result = cursor.fetchone()
        if result:
            found_data = f"Stok {result[0]} saat ini tersedia {result[1]} unit."

    # Pencarian untuk detail produk (deskripsi) atau nama produk
    elif "detail" in query_lower or "jelaskan" in query_lower or "apa itu" in query_lower or "nama produk" in query_lower:
        print("[RAG Server] Masuk ke blok 'detail/penjelasan'") # Debug print
        cursor.execute("SELECT name, description FROM products WHERE LOWER(name) LIKE ? OR LOWER(product_code) LIKE ?", ('%' + product_search_term + '%', '%' + product_search_term + '%',))
        result = cursor.fetchone()
        if result:
            found_data = f"Detail {result[0]}: {result[1]}"
    
    # Jika tidak ada match spesifik di atas, coba cari nama atau kode produk secara umum
    if found_data == "Tidak ada data relevan dari database.":
        print("[RAG Server] Masuk ke blok 'pencarian umum'") # Debug print
        cursor.execute("SELECT name, description, price, stock FROM products WHERE LOWER(name) LIKE ? OR LOWER(product_code) LIKE ?", ('%' + product_search_term + '%', '%' + product_search_term + '%',))
        result = cursor.fetchone()
        if result:
            # Format respons yang lebih komprehensif jika ditemukan
            found_data = (
                f"Informasi Produk: {result[0]}. "
                f"Deskripsi: {result[1]}. "
                f"Harga: ${result[2]:.2f}. "
                f"Stok: {result[3]} unit."
            )

    conn.close()
    
    print(f"[RAG Server] Mengembalikan data: '{found_data}'")
    return jsonify({"data": found_data})

if __name__ == '__main__':
    # Inisialisasi database saat aplikasi dimulai
    init_db()
    print("Memulai MCP Server RAG di http://127.0.0.1:5001")
    app.run(port=5001, debug=True) # debug=True hanya untuk pengembangan
