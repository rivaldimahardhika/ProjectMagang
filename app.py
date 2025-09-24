from flask import Flask, render_template, Response, request, redirect, url_for, session, flash, send_file, jsonify
from ultralytics import YOLO
import cv2, numpy as np, os, time
import io, traceback
from utils.detector import ObjectDetector
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
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

# ======================
# MODELS
# ======================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class DetectionSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    object_name = db.Column(db.String(120), nullable=False)
    object_count = db.Column(db.Integer, nullable=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('summaries', lazy=True))


# ======================
# DETECTOR
# ======================
detector = ObjectDetector("models/best.pt")  # Load YOLO lewat class custom
last_saved_time = 0  # timestamp terakhir insert


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
            session["user_id"] = user.id
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


@app.route("/detect_api", methods=["POST"])
def detect_api():
    try:
        if "frame" not in request.files:
            return jsonify({"error": "No frame uploaded"}), 400

        # Baca file & konversi ke OpenCV
        file = request.files["frame"].read()
        npimg = np.frombuffer(file, np.uint8)
        frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"error": "Invalid image"}), 400

        # Jalankan YOLO
        results = detector.model(frame)
        count = len(results[0].boxes)  # jumlah deteksi

        # Plot hasil
        annotated_frame = results[0].plot()

        # Encode ke JPEG
        ok, buffer = cv2.imencode(".jpg", annotated_frame)
        if not ok:
            return jsonify({"error": "Encode failed"}), 500

        # Bungkus response + header count
        response = Response(buffer.tobytes(), mimetype="image/jpeg")
        response.headers["X-Count"] = str(count)
        return response

    except Exception as e:
        traceback.print_exc()  # biar error tetap kelihatan di log server
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
