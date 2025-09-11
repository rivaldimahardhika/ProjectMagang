from flask import Flask, render_template, Response, request
import cv2
import numpy as np
from utils.detector import ObjectDetector

app = Flask(__name__)
detector = ObjectDetector("models/best.pt")

@app.route("/")
def index():
    return render_template("base.html")

@app.route("/monitor")
def monitor():
    return render_template("monitor.html")

@app.route("/detect")
def detect():
    return render_template("detect.html")

@app.route("/detect_api", methods=["POST"])
def detect_api():
    file = request.files['frame'].read()
    npimg = np.frombuffer(file, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    frame = detector.detect(frame)

    print("Frame diproses...")
    
    _, buffer = cv2.imencode('.jpg', frame)
    return buffer.tobytes(), 200, {'Content-Type': 'image/jpeg'}

if __name__ == "__main__":
    app.run(debug=True)