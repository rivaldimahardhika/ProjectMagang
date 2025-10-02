from app import app, db, User, Gudang

def create_user(username, password, nama_gudang, lokasi, kapasitas):
    with app.app_context():
        # cek username duplikat     
        if User.query.filter_by(username=username).first():
            print("❌ Username sudah ada!")
            return

        # buat user baru
        new_user = User(username=username,)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        # buat gudang untuk user tsb (pakai id_user yang benar)
        new_gudang = Gudang(
            nama_gudang=nama_gudang,
            lokasi=lokasi,
            kapasitas=kapasitas,
            id_user=new_user.id_user   # 🔑 ini diperbaiki
        )
        db.session.add(new_gudang)
        db.session.commit()

        print(f"✅ User '{username}' berhasil dibuat dengan gudang '{nama_gudang}'.")

if __name__ == "__main__":
    username = input("Masukkan username baru: ")
    password = input("Masukkan password: ")
    nama_gudang = input("Masukkan nama gudang: ")
    lokasi = input("Masukkan lokasi gudang: ")
    kapasitas = int(input("Masukkan kapasitas gudang: "))

    create_user(username, password, nama_gudang, lokasi, kapasitas)
