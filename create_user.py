from app import app, db, User, Gudang
from werkzeug.security import generate_password_hash

def create_user():
    print("=== Buat User Baru ===")

    # 🔹 1️⃣ Pilih role dulu
    role = input("Pilih role (admin/operator): ").strip().lower()

    if role not in ["admin", "operator"]:
        print("❌ Role tidak valid! Pilih 'admin' atau 'operator'.")
        return

    # 🔹 2️⃣ Masukkan username & password
    username = input("Masukkan username: ").strip()
    password = input("Masukkan password: ").strip()

    # Cek apakah username sudah digunakan
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        print("❌ Username sudah digunakan.")
        return

    # 🔹 3️⃣ Buat user baru
    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        status=True
    )

    db.session.add(new_user)
    db.session.commit()
    print(f"✅ User '{username}' ({role}) berhasil dibuat.")

    # 🔹 4️⃣ Jika role operator, minta data gudang
    if role == "operator":
        nama_gudang = input("Masukkan nama gudang: ").strip()
        lokasi = input("Masukkan lokasi gudang: ").strip()
        kapasitas_str = input("Masukkan kapasitas gudang (angka): ").strip()

        try:
            kapasitas = int(kapasitas_str)
        except ValueError:
            print("⚠️ Kapasitas harus berupa angka. Proses dibatalkan.")
            db.session.rollback()
            return

        gudang = Gudang(
            nama_gudang=nama_gudang,
            lokasi=lokasi,
            kapasitas=kapasitas,
            id_user=new_user.id_user
        )

        db.session.add(gudang)
        db.session.commit()
        print(f"✅ Gudang '{nama_gudang}' berhasil ditautkan ke operator '{username}'.")

if __name__ == "__main__":
    # Pastikan dijalankan dalam konteks Flask
    with app.app_context():
        create_user()
