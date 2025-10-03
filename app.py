from flask import Flask, render_template, Response, request, redirect, url_for, session, flash, send_file, jsonify
from ultralytics import YOLO
import cv2, numpy as np, os, time
import io, traceback
from utils.detector import ObjectDetector
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load env
load_dotenv()

app = Flask(__name__)

# Config
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("SECRET_KEY", "default_secret")

# Init DB
db = SQLAlchemy(app)
migrate = Migrate(app, db)
WIB = timezone(timedelta(hours=7))

# ======================
# MODELS
# ======================
class User(db.Model):
    __tablename__ = "users"
    id_user = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    gudang = db.relationship("Gudang", backref="user", lazy=True)

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
    id_user = db.Column(db.Integer, db.ForeignKey("users.id_user"), nullable=False)

    cctvs = db.relationship("CCTV", backref="gudang", lazy=True)


class Karung(db.Model):
    __tablename__ = "karung"
    id_karung = db.Column(db.Integer, primary_key=True)
    nama_karung = db.Column(db.String(120), nullable=False)

    deteksi = db.relationship("Deteksi", backref="karung", lazy=True)


class CCTV(db.Model):
    __tablename__ = "cctv"
    id_cctv = db.Column(db.Integer, primary_key=True)
    nama_cctv = db.Column(db.String(120), nullable=False)
    id_gudang = db.Column(db.Integer, db.ForeignKey("gudang.id_gudang"), nullable=False)

    deteksi = db.relationship("Deteksi", backref="cctv", lazy=True)


class Deteksi(db.Model):
    __tablename__ = "deteksi"
    id_deteksi = db.Column(db.Integer, primary_key=True)
    waktu = db.Column(db.DateTime, default=lambda: datetime.now(WIB))
    id_cctv = db.Column(db.Integer, db.ForeignKey("cctv.id_cctv"), nullable=False)
    id_karung = db.Column(db.Integer, db.ForeignKey("karung.id_karung"), nullable=False)
    total_karung = db.Column(db.Integer, nullable=False)
    data_encrypted = db.Column(db.LargeBinary) 

# ======================
# DETECTOR
# ======================
detector = ObjectDetector("models/best.pt")  # Load YOLO lewat class custom

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
def monitor():
    if "user_id" not in session:
        flash("Silakan login untuk mengakses halaman ini", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template("monitor.html", user=user)


@app.route("/detect")
def detect():
    if "user_id" not in session:
        flash("Silakan login untuk mengakses halaman ini", "warning")
        return redirect(url_for("login"))

    cam_id = request.args.get("cam_id", "0")  # default webcam
    user = User.query.get(session["user_id"])
    return render_template("detect.html", user=user, cam_id=cam_id)



@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Silakan login untuk mengakses halaman ini", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template("dashboard.html", user=user)


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
        if user and user.check_password(password):
            session["user_id"] = user.id_user   # ✅ pakai id_user

            flash("Login berhasil!", "success")
            return redirect(url_for("home"))
        else:
            flash("Login gagal! Username atau password salah", "danger")
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

    data = request.json
    nama_cctv = data.get("nama_cctv")
    id_gudang = data.get("id_gudang")

    if not nama_cctv or not id_gudang:
        return jsonify({"error": "Incomplete data"}), 400

    # 🔍 cek apakah kamera ini sudah ada untuk gudang tersebut
    existing_cctv = CCTV.query.filter_by(nama_cctv=nama_cctv, id_gudang=id_gudang).first()

    if existing_cctv:
        return jsonify({
            "status": "exists",
            "id_cctv": existing_cctv.id_cctv
        })

    # 🚀 kalau belum ada → insert baru
    new_cctv = CCTV(nama_cctv=nama_cctv, id_gudang=id_gudang)
    db.session.add(new_cctv)
    db.session.commit()

    return jsonify({
        "status": "created",
        "id_cctv": new_cctv.id_cctv
    })

@app.route("/save_detection", methods=["POST"])
def save_detection():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    id_cctv = data.get("id_cctv")
    total_karung = data.get("total_karung")

    if not id_cctv or not total_karung:
        return jsonify({"error": "Incomplete data"}), 400

    deteksi = Deteksi(
        waktu=datetime.now(),
        id_cctv=id_cctv,
        id_karung=None,  # isi sesuai hasil deteksi karung
        total_karung=total_karung,
        data_encrypted=None
    )
    db.session.add(deteksi)
    db.session.commit()

    return jsonify({"status": "ok", "id_deteksi": deteksi.id_deteksi})


SAVE_TO_DB = True  # default aktif
last_saved_time = 0  # global timer
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

        # === Ambil frame dari request ===
        file = request.files["frame"].read()
        npimg = np.frombuffer(file, np.uint8)
        frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

        # === Ambil id_cctv dari FormData ===
        id_cctv = request.form.get("id_cctv")
        if not id_cctv:
            return jsonify({"error": "id_cctv not provided"}), 400

        try:
            id_cctv = int(id_cctv)
        except ValueError:
            return jsonify({"error": "Invalid id_cctv"}), 400

        # === Jalankan YOLO ===
        annotated_frame, counts = detector.detect(frame)
        total_count = sum(counts.values())

        object_name = "none"
        if counts:
            object_name = list(counts.keys())[0]  # ambil nama objek hasil deteksi

        current_time = time.time()

        # === Simpan ke DB (setiap 10 detik) ===
        if SAVE_TO_DB and "user_id" in session and current_time - last_saved_time >= 10:
            # cek apakah CCTV dengan id ini valid
            cctv = CCTV.query.get(id_cctv)
            if cctv:
                # Cari id_karung dari tabel Karung berdasarkan nama
                karung = Karung.query.filter_by(nama_karung=object_name).first()
                if not karung:
                    # kalau nama karung belum ada → auto insert
                    karung = Karung(nama_karung=object_name)
                    db.session.add(karung)
                    db.session.commit()

                # Simpan deteksi
                new_deteksi = Deteksi(
                    waktu=datetime.now(WIB),
                    id_cctv=id_cctv,
                    id_karung=karung.id_karung, 
                    total_karung=total_count,
                    data_encrypted=None
                )
                db.session.add(new_deteksi)
                db.session.commit()
                last_saved_time = current_time

        # === Kirim balik frame hasil anotasi ke browser ===
        ok, buffer = cv2.imencode(".jpg", annotated_frame)
        response = Response(buffer.tobytes(), mimetype="image/jpeg")
        response.headers["X-Count"] = str(total_count)
        return response

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
