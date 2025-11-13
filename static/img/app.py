from flask import Flask, render_template, Response, request, redirect, url_for, session, flash, send_file, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from ultralytics import YOLO
import cv2, numpy as np, os, time
import io, traceback, jwt
import json 
from utils.detector import ObjectDetector
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from utils.encryption import aes_gcm_encrypt, aes_gcm_decrypt, hybrid_encrypt_bytes, hybrid_decrypt_bytes, load_rsa_private
from utils.helpers import role_required

# =====================================
# Load Environment Variables
# =====================================
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# =====================================
# Init Flask-Login
# =====================================
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # redirect ke halaman login bila belum login

# =====================================
# Init Database
# =====================================
db = SQLAlchemy(app)
migrate = Migrate(app, db)
WIB = timezone(timedelta(hours=7))

# =====================================
# MODELS
# =====================================
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id_user = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="gudang") 

    gudang = db.relationship("Gudang", backref="user", lazy=True)

    def set_password(self, plain_password):
        self.password = generate_password_hash(plain_password)

    def check_password(self, plain_password):
        return check_password_hash(self.password, plain_password)

    def get_id(self):
        return str(self.id_user)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Gudang(db.Model):
    __tablename__ = "gudang"
    id_gudang = db.Column(db.Integer, primary_key=True)
    nama_gudang = db.Column(db.String(120), nullable=False)
    lokasi = db.Column(db.String(120), nullable=False)
    kapasitas = db.Column(db.Integer, nullable=False)
    id_user = db.Column(db.Integer, db.ForeignKey("users.id_user"), nullable=False)

    dek_encrypted = db.Column(db.LargeBinary, nullable=True)   # AES key terenkripsi (RSA)
    dek_version = db.Column(db.Integer, default=1)
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
    id_karung = db.Column(db.Integer, db.ForeignKey("karung.id_karung"), nullable=True)
    total_karung = db.Column(db.Integer, nullable=False, default=0)

    data_encrypted = db.Column(db.LargeBinary, nullable=True)
    nonce = db.Column(db.LargeBinary, nullable=True)
    tag = db.Column(db.LargeBinary, nullable=True)
    total_karung_plain = db.Column(db.Integer, nullable=False, default=0)

# =====================================
# Detector
# =====================================
detector = ObjectDetector("models/best.pt")

# Konfigurasi Metabase Secure Embed
# =====================================
METABASE_SITE_URL = os.getenv("METABASE_SITE_URL")
METABASE_SECRET_KEY = os.getenv("METABASE_SECRET_KEY")
METABASE_DASHBOARD_ID = int(os.getenv("METABASE_DASHBOARD_ID", "1"))
METABASE_PUBLIC_URL = os.getenv("METABASE_PUBLIC_URL", "http://localhost:3000/public/dashboard/d56850f9-347f-4db4-abfa-d8f305326c54")

# =====================================
# ROUTES
# =====================================
@app.route("/")
def home():
    if current_user.is_authenticated:
        role = current_user.role
        id_gudang = session.get("id_gudang")
        return render_template("home.html", role=role, id_gudang=id_gudang)
    return render_template("home.html")

# ========================
# LOGIN / LOGOUT
# ========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username dan password wajib diisi", "danger")
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)

            # ambil id_gudang berdasar id_user
            gudang = Gudang.query.filter_by(id_user=user.id_user).first()
            session["id_gudang"] = gudang.id_gudang if gudang else None

            print(f"[DEBUG] id_gudang dari gudang: {session.get('id_gudang')}")

            return redirect(url_for("home"))

        flash("Username atau password salah", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Anda berhasil logout", "info")
    return redirect(url_for("home"))

# ========================
# HALAMAN LAIN
# ========================
@app.route("/monitor")
@login_required
def monitor():
    return render_template("monitor.html", user=current_user)

@app.route("/detect")
@login_required
def detect():
    cam_id = request.args.get("cam_id", "0")
    return render_template("detect.html", user=current_user, cam_id=cam_id)

# ========================
# DASHBOARD
# ========================
@app.route("/dashboard")
@login_required
def dashboard():
    # Ambil data dari user dan session
    role = current_user.role
    id_user = current_user.id_user
    nama_gudang = session.get("nama_gudang")  # ubah dari id_gudang ke nama_gudang

    # Tentukan dashboard berdasarkan role
    if role == "Admin":
        # Admin melihat semua data
        iframe_url = "http://localhost:3000/public/dashboard/d56850f9-347f-4db4-abfa-d8f305326c54"
    elif role == "Operator":
        # Operator hanya melihat data gudangnya sendiri
        if nama_gudang:
            iframe_url = (
                f"http://localhost:3000/public/dashboard/657adfda-147a-4042-a795-c05c509b8491?"
                f"id_user={id_user}&lokasi={nama_gudang}"
            )
        else:
            # Jika session nama_gudang belum terset
            iframe_url = (
                f"http://localhost:3000/public/dashboard/657adfda-147a-4042-a795-c05c509b8491?"
                f"id_user={id_user}"
            )
    else:
        return "Role tidak dikenali", 403

    # Debugging untuk memastikan parameter benar
    print(f"[DEBUG] Role: {role}")
    print(f"[DEBUG] id_user: {id_user}")
    print(f"[DEBUG] nama_gudang: {nama_gudang}")
    print(f"[DEBUG] Iframe URL: {iframe_url}")

    # Render dashboard
    return render_template("dashboard.html", iframe_url=iframe_url)


@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user)

# ========================
# API CCTV & DETEKSI
# ========================
@app.route("/register_cctv", methods=["POST"])
@login_required
def register_cctv():
    data = request.json
    nama_cctv = data.get("nama_cctv")
    id_gudang = data.get("id_gudang")

    if not nama_cctv or not id_gudang:
        return jsonify({"error": "Incomplete data"}), 400

    existing_cctv = CCTV.query.filter_by(nama_cctv=nama_cctv, id_gudang=id_gudang).first()
    if existing_cctv:
        return jsonify({"status": "exists", "id_cctv": existing_cctv.id_cctv})

    new_cctv = CCTV(nama_cctv=nama_cctv, id_gudang=id_gudang)
    db.session.add(new_cctv)
    db.session.commit()

    return jsonify({"status": "created", "id_cctv": new_cctv.id_cctv})

@app.route("/save_detection", methods=["POST"])
@login_required
def save_detection():
    data = request.json
    id_cctv = data.get("id_cctv")
    total_karung = data.get("total_karung")

    if not id_cctv or not total_karung:
        return jsonify({"error": "Incomplete data"}), 400

    deteksi = Deteksi(
        waktu=datetime.now(WIB),
        id_cctv=id_cctv,
        total_karung=total_karung,
        total_karung_plain=total_karung
    )
    db.session.add(deteksi)
    db.session.commit()
    return jsonify({"status": "ok", "id_deteksi": deteksi.id_deteksi})

# ========================
# DETEKSI API
# ========================
SAVE_TO_DB = True
last_saved_time = 0

@app.route("/detect_api", methods=["POST"])
@login_required
def detect_api():
    global last_saved_time
    try:
        file = request.files.get("frame")
        if not file:
            return jsonify({"error": "No frame uploaded"}), 400

        id_cctv = request.form.get("id_cctv", type=int)
        if not id_cctv:
            return jsonify({"error": "id_cctv not provided"}), 400

        npimg = np.frombuffer(file.read(), np.uint8)
        frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        annotated_frame, counts = detector.detect(frame)
        total_count = sum(counts.values())
        object_name = next(iter(counts), "none")

        if SAVE_TO_DB and time.time() - last_saved_time >= 10:
            cctv = CCTV.query.get(id_cctv)
            if not cctv:
                return jsonify({"error": "CCTV not found"}), 404

            karung = Karung.query.filter_by(nama_karung=object_name).first()
            if not karung:
                karung = Karung(nama_karung=object_name)
                db.session.add(karung)
                db.session.commit()

            gudang = cctv.gudang
            data_encrypted, nonce, tag = None, None, None

            if gudang and getattr(gudang, "dek_encrypted", None):
                rsa_priv = load_rsa_private("keys/private_key.pem")
                from Crypto.Cipher import PKCS1_OAEP
                cipher_rsa = PKCS1_OAEP.new(rsa_priv)

                try:
                    dek = cipher_rsa.decrypt(gudang.dek_encrypted)
                    payload = json.dumps({
                        "total_karung": total_count,
                        "waktu": datetime.now(WIB).isoformat(),
                        "nama_karung": object_name
                    }).encode("utf-8")
                    data_encrypted, nonce, tag = aes_gcm_encrypt(payload, dek)
                except Exception as e:
                    app.logger.error("Encryption failed: %s", e)

            new_deteksi = Deteksi(
                waktu=datetime.now(WIB),
                id_cctv=id_cctv,
                id_karung=karung.id_karung,
                total_karung=total_count,
                data_encrypted=data_encrypted,
                nonce=nonce,
                tag=tag,
                total_karung_plain=total_count
            )
            db.session.add(new_deteksi)
            db.session.commit()
            last_saved_time = time.time()

        ok, buffer = cv2.imencode(".jpg", annotated_frame)
        resp = Response(buffer.tobytes(), mimetype="image/jpeg")
        resp.headers["X-Count"] = str(total_count)
        return resp

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ========================
# DECRYPT DETEKSI
# ========================
@app.route("/decrypt_deteksi/<int:id_deteksi>")
@login_required
def decrypt_deteksi(id_deteksi):
    user = current_user
    d = Deteksi.query.get(id_deteksi)
    if not d:
        return jsonify({"error":"Not found"}), 404

    cctv = CCTV.query.get(d.id_cctv)
    if not cctv:
        return jsonify({"error":"CCTV not found"}), 404
    gudang = Gudang.query.get(cctv.id_gudang)

    if user.role.lower() != "admin":
        if not gudang or gudang.id_user != user.id_user:
            return jsonify({"error":"Forbidden"}), 403

    if not gudang.dek_encrypted:
        return jsonify({"error":"No DEK configured for this gudang"}), 500

    try:
        rsa_priv = load_rsa_private("keys/private_key.pem")
        from Crypto.Cipher import PKCS1_OAEP
        cipher_rsa = PKCS1_OAEP.new(rsa_priv)
        dek = cipher_rsa.decrypt(gudang.dek_encrypted)
        plaintext = aes_gcm_decrypt(d.data_encrypted, d.nonce, d.tag, dek)
        payload = json.loads(plaintext.decode("utf-8"))
        return jsonify({"ok": True, "payload": payload})
    except Exception as e:
        app.logger.error("Encryption failed: %s", e)
        return jsonify({"error": str(e)}), 500

# =====================================
# RUN APP
# =====================================
if __name__ == "__main__":
    app.run(debug=True)
