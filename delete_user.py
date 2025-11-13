from app import app, db, User, Gudang, CCTV, Deteksi
from sqlalchemy.exc import SQLAlchemyError

def delete_user(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"❌ User '{username}' tidak ditemukan.")
        return

    print(f"⚠️ Menghapus user '{username}' (role: {user.role}) beserta semua data terkait...")

    try:
        # 1️⃣ Ambil semua gudang milik user (jika ada)
        gudangs = Gudang.query.filter_by(id_user=user.id_user).all()

        for gudang in gudangs:
            # 2️⃣ Hapus semua deteksi yang terkait dengan CCTV di gudang ini
            for cctv in gudang.cctvs:
                deleted_deteksi = Deteksi.query.filter_by(id_cctv=cctv.id_cctv).delete()
                print(f"   - Menghapus {deleted_deteksi} data deteksi untuk CCTV '{cctv.nama_cctv}'")
                db.session.delete(cctv)

            print(f"   - Menghapus gudang '{gudang.nama_gudang}'")
            db.session.delete(gudang)

        # 3️⃣ Hapus user
        print(f"🗑️  Menghapus user '{username}'...")
        db.session.delete(user)
        db.session.commit()

        print(f"✅ User '{username}' dan semua data terkait berhasil dihapus.")

    except SQLAlchemyError as e:
        db.session.rollback()
        print("❌ Terjadi kesalahan saat menghapus user:", str(e))

confirm = input(f"Yakin ingin menghapus user '{uname}' beserta semua datanya? (y/n): ").lower()
if confirm == "y":
    with app.app_context():
        delete_user(uname)
else:
    print("❎ Dibatalkan.")


if __name__ == "__main__":
    uname = input("Masukkan username user yang ingin dihapus: ").strip()
    # Jalankan fungsi dalam konteks Flask
    with app.app_context():
        delete_user(uname)
