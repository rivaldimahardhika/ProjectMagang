from flask import Flask, render_template, Response, request, redirect, url_for, session, flash, jsonify
from ultralytics import YOLO
import cv2, numpy as np, os, time, traceback
import os, jwt, time
from utils.detector import ObjectDetector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from functools import wraps
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# ======================
# CONFIGURASI AWAL
# ======================
# load .env (jika belum)
load_dotenv()   

# gunakan config.py
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.logger.info(f"Database Connected: {app.config['SQLALCHEMY_DATABASE_URI']}")

# safety: jika SECRET_KEY default masih digunakan, beri peringatan di log (opsional)
if app.config.get("SECRET_KEY", "") in ("", "please-change-this-in-prod", "default_secret"):
    app.logger.warning("SECRET_KEY is using default value. Change it in your .env for production!")

# Session lifetime
app.permanent_session_lifetime = timedelta(hours=1)

# init extensions
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Timezone WIB (jika butuh)
WIB = timezone(timedelta(hours=7))

# Encryption key: ambil dari config, jika kosong => generate (only for dev)
from cryptography.fernet import Fernet

raw_key = app.config.get("ENCRYPTION_KEY") or ""
if raw_key:
    # jika disimpan di .env sebagai string base64, pastikan bytes
    if isinstance(raw_key, str):
        ENCRYPTION_KEY = raw_key.strip().encode()
    else:
        ENCRYPTION_KEY = raw_key
else:
    # hanya generate key kalau benar-benar tidak ada (development)
    ENCRYPTION_KEY = Fernet.generate_key()
    app.logger.warning("ENCRYPTION_KEY not found in env. Generated temporary key (will not persist across restarts).")

fernet = Fernet(Config.ENCRYPTION_KEY.encode())

# GLOBALS
SAVE_TO_DB = True
last_saved_time = 0

# ======================
# MODELS
# ======================
class User(db.Model):
    __tablename__ = "users"
    id_user = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="operator")
    last_login = db.Column(db.DateTime, default=None)
    status = db.Column(db.Boolean, default=True)

    gudang = db.relationship(
        "Gudang",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Gudang(db.Model):
    __tablename__ = "gudang"
    id_gudang = db.Column(db.Integer, primary_key=True)
    nama_gudang = db.Column(db.String(120), nullable=False)
    lokasi = db.Column(db.String(120), nullable=False)
    kapasitas = db.Column(db.Integer, nullable=False)

    id_user = db.Column(
        db.Integer,
        db.ForeignKey("users.id_user", ondelete="CASCADE"),
        nullable=False
    )

    cctvs = db.relationship(
        "CCTV",
        backref="gudang",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Karung(db.Model):
    __tablename__ = "karung"
    id_karung = db.Column(db.Integer, primary_key=True)
    nama_karung = db.Column(db.String(120), nullable=False)

    deteksi = db.relationship("Deteksi", backref="karung", lazy=True)


class CCTV(db.Model):
    __tablename__ = "cctv"
    id_cctv = db.Column(db.Integer, primary_key=True)
    nama_cctv = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(100), nullable=True)

    id_gudang = db.Column(
        db.Integer,
        db.ForeignKey("gudang.id_gudang", ondelete="CASCADE"),
        nullable=False
    )

    deteksi = db.relationship(
        "Deteksi",
        backref="cctv",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Deteksi(db.Model):
    __tablename__ = "deteksi"
    id_deteksi = db.Column(db.Integer, primary_key=True)
    waktu = db.Column(db.DateTime, default=lambda: datetime.now(WIB))
    total_karung = db.Column(db.Integer, nullable=False)
    data_encrypted = db.Column(db.LargeBinary, nullable=True)
    encrypted_dek = db.Column(db.LargeBinary, nullable=True)

    id_cctv = db.Column(
        db.Integer,
        db.ForeignKey("cctv.id_cctv", ondelete="CASCADE"),
        nullable=False
    )

    id_karung = db.Column(
        db.Integer,
        db.ForeignKey("karung.id_karung"),
        nullable=True
    )



# ======================
# DECORATOR ROLE-BASED ACCESS
# ======================
def role_required(role):
    """Batasi akses halaman hanya untuk role tertentu"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Silakan login terlebih dahulu", "warning")
                return redirect(url_for("login"))
            user = User.query.get(session["user_id"])
            if user.role != role:
                flash("Anda tidak memiliki izin untuk mengakses halaman ini", "danger")
                return redirect(url_for("home"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ======================
# DETECTOR YOLO
# ======================
detector = ObjectDetector("models/best.pt")

# ======================
# ROUTES
# ======================

@app.route("/")
def home():
    user = None
    if "user_id" in session:
        user = User.query.get(session["user_id"])
    return render_template("home.html", user=user)


@app.route("/monitor")
@role_required("operator")
def monitor():
    if "user_id" not in session:
        flash("Silakan login untuk mengakses halaman ini", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template("monitor.html", user=user)


@app.route("/detect")
@role_required("operator")
def detect():
    if "user_id" not in session:
        flash("Silakan login untuk mengakses halaman ini", "warning")
        return redirect(url_for("login"))

    cam_id = request.args.get("cam_id", "0")
    user = User.query.get(session["user_id"])
    return render_template("detect.html", user=user, cam_id=cam_id)

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Silakan login dulu", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    deteksi_data = Deteksi.query.order_by(Deteksi.waktu.desc()).all()

    # 🔐 Dekripsi data deteksi (tetap sama)
    decrypted_records = []
    for d in deteksi_data:
        try:
            decrypted = fernet.decrypt(d.data_encrypted).decode() if d.data_encrypted else "{}"
        except Exception:
            decrypted = "{}"
        decrypted_records.append({
            "id_deteksi": d.id_deteksi,
            "waktu": d.waktu,
            "id_cctv": d.id_cctv,
            "id_karung": d.id_karung,
            "total_karung": d.total_karung,
            "data_terdekripsi": decrypted
        })

    # 🌐 URL Metabase Dashboard
    BASE_METABASE_URL_ADMIN = "http://localhost:3000/public/dashboard/b78035aa-565a-4e82-88a1-a150e2c8fc25"
    BASE_METABASE_URL_OPERATOR = "http://localhost:3000/public/dashboard/5fd53798-2e91-4fdb-a007-a40889fd793c"

    # 📊 Pilih dashboard sesuai role
    if user.role.lower() == "admin":
        iframe_url = BASE_METABASE_URL_ADMIN
    else:
        # Ambil gudang berdasarkan user
        gudang = Gudang.query.filter_by(id_user=user.id_user).first()
        if not gudang:
            flash("Gudang tidak ditemukan untuk user ini", "danger")
            return redirect(url_for("home"))

        # Tambahkan parameter id_user untuk filter otomatis di Metabase
        iframe_url = f"{BASE_METABASE_URL_OPERATOR}?id_user={user.id_user}"

    app.logger.info(f"[DASHBOARD] User={user.username}, Role={user.role}, URL={iframe_url}")

    return render_template(
        "dashboard.html",
        user=user,
        deteksi=decrypted_records,
        iframe_url=iframe_url
    )



@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/profile")
def profile():
    if "user_id" not in session:
        flash("Silakan login dulu", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template("profile.html", user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        # Cek user ada & aktif
        if not user:
            flash("Username tidak ditemukan", "danger")
            return redirect(url_for("login"))
        if not user.status:
            flash("Akun Anda dinonaktifkan. Hubungi admin.", "danger")
            return redirect(url_for("login"))

        # Cek password
        if user and user.check_password(password):
            # Update waktu login terakhir
            user.last_login = datetime.now(WIB)
            db.session.commit()

            session.permanent = True
            session["user_id"] = user.id_user

            flash("Login berhasil!", "success")
            return redirect(url_for("home"))
        else:
            flash("Password salah!", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Anda berhasil logout", "success")
    return redirect(url_for("home"))


@app.route("/register_cctv", methods=["POST"])
def register_cctv():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    user = User.query.get(session["user_id"])
    data = request.json
    nama_cctv = data.get("nama_cctv")
    id_gudang = data.get("id_gudang")
    ip_address = data.get("ip_address", None)

    if not nama_cctv or not id_gudang:
        return jsonify({"error": "Incomplete data"}), 400

    # jika operator, pastikan id_gudang milik user tersebut
    if user.role == "operator":
        gudang_operator = Gudang.query.filter_by(id_user=user.id_user).first()
        if not gudang_operator or gudang_operator.id_gudang != int(id_gudang):
            return jsonify({"error": "Anda tidak memiliki izin menambah CCTV di gudang ini"}), 403

    # cek CCTV sudah ada untuk gudang ini
    existing_cctv = CCTV.query.filter_by(nama_cctv=nama_cctv, id_gudang=id_gudang).first()
    if existing_cctv:
        return jsonify({"status": "exists", "id_cctv": existing_cctv.id_cctv})

    new_cctv = CCTV(nama_cctv=nama_cctv, id_gudang=id_gudang, ip_address=ip_address)
    db.session.add(new_cctv)
    db.session.commit()

    return jsonify({"status": "created", "id_cctv": new_cctv.id_cctv})


@app.route("/save_detection", methods=["POST"])
def save_detection():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    id_cctv = data.get("id_cctv")
    total_karung = data.get("total_karung")
    hasil_deteksi = data.get("hasil_deteksi", {})

    if not id_cctv or not total_karung:
        return jsonify({"error": "Incomplete data"}), 400

    encrypted_data = fernet.encrypt(str(hasil_deteksi).encode())

    deteksi = Deteksi(
        waktu=datetime.now(WIB),
        id_cctv=id_cctv,
        id_karung=None,
        total_karung=total_karung,
        data_encrypted=encrypted_data
    )
    db.session.add(deteksi)
    db.session.commit()

    return jsonify({"status": "ok", "id_deteksi": deteksi.id_deteksi})


@app.route("/toggle_db", methods=["POST"])
def toggle_db():
    global SAVE_TO_DB
    data = request.json
    SAVE_TO_DB = data.get("save", True)
    return jsonify({"status": "ok", "save_to_db": SAVE_TO_DB})


@app.route("/detect_api", methods=["POST"])
def detect_api():
    global last_saved_time
    try:
        if "frame" not in request.files:
            return jsonify({"error": "No frame uploaded"}), 400

        file = request.files["frame"].read()
        npimg = np.frombuffer(file, np.uint8)
        frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

        id_cctv = request.form.get("id_cctv")
        if not id_cctv:
            return jsonify({"error": "id_cctv not provided"}), 400
        id_cctv = int(id_cctv)

        annotated_frame, counts = detector.detect(frame)
        total_count = sum(counts.values())
        object_name = list(counts.keys())[0] if counts else "none"
        current_time = time.time()

        if SAVE_TO_DB and "user_id" in session and current_time - last_saved_time >= 10:
            cctv = CCTV.query.get(id_cctv)
            if cctv:
                # cek atau buat karung
                karung = Karung.query.filter_by(nama_karung=object_name).first()
                if not karung:
                    karung = Karung(nama_karung=object_name)
                    db.session.add(karung)
                    db.session.commit()

                # ============================
                # Envelope Encryption
                # ============================
                # 1. Generate DEK (data encryption key) per deteksi
                dek = Fernet.generate_key()
                f_dek = Fernet(dek)

                # 2. Encrypt data (counts dict)
                encrypted_data = f_dek.encrypt(str(counts).encode())

                # 3. Encrypt DEK dengan master key
                f_master = Fernet(ENCRYPTION_KEY)
                encrypted_dek = f_master.encrypt(dek)

                # ============================
                # Simpan ke DB
                # ============================
                new_deteksi = Deteksi(
                    waktu=datetime.now(WIB),
                    id_cctv=id_cctv,
                    id_karung=karung.id_karung,
                    total_karung=total_count,
                    data_encrypted=encrypted_data,
                    encrypted_dek=encrypted_dek
                )
                db.session.add(new_deteksi)
                db.session.commit()
                last_saved_time = current_time

        # Encode annotated frame sebagai JPEG
        ok, buffer = cv2.imencode(".jpg", annotated_frame)
        response = Response(buffer.tobytes(), mimetype="image/jpeg")
        response.headers["X-Count"] = str(total_count)
        return response

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ======================
# RUN SERVER
# ======================
if __name__ == "__main__":
    app.run(debug=True)
