from app import app, db, User
from werkzeug.security import generate_password_hash

def create_user(username, password):
    with app.app_context():  # masuk ke context Flask
        if User.query.filter_by(username=username).first():
            print("❌ Username sudah ada!")
            return
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        print(f"✅ User '{username}' berhasil dibuat.")

if __name__ == "__main__":
    # minta input dari terminal
    username = input("Masukkan username baru: ")
    password = input("Masukkan password: ")
    create_user(username, password)
