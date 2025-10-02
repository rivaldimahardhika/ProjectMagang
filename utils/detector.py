from ultralytics import YOLO
import cv2
import numpy as np
from collections import defaultdict
from datetime import datetime
import time   # ✅ untuk hitung FPS

class ObjectDetector:
    def __init__(self, model_path="models/best.pt", conf_thresh=0.5):
        self.model = YOLO(model_path, task="detect")
        self.labels = self.model.names
        self.conf_thresh = conf_thresh

        # Warna kotak (Tableau 10)
        self.bbox_colors = [
            (164,120,87), (68,148,228), (93,97,209), (178,182,133),
            (88,159,106), (96,202,231), (159,124,168), (169,162,241),
            (98,118,150), (172,176,184)
        ]

    def detect(self, frame):
        start_time = time.time()   # ✅ mulai hitung FPS

        results = self.model(frame, conf=self.conf_thresh, verbose=False)
        detections = results[0].boxes

        # Hitung jumlah objek
        stable_counts = defaultdict(int)

        for i, box in enumerate(detections):
            xyxy = box.xyxy.cpu().numpy().squeeze().astype(int)
            xmin, ymin, xmax, ymax = xyxy
            conf = box.conf.item()
            class_id = int(box.cls.item())
            class_name = self.labels[class_id]

            if conf >= self.conf_thresh:
                color = self.bbox_colors[class_id % len(self.bbox_colors)]
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)

                label = f"{class_name}: {conf:.2f}"
                (label_w, label_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (xmin, ymin - label_h - 10),
                              (xmin + label_w, ymin), color, cv2.FILLED)
                cv2.putText(frame, label, (xmin, ymin - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)

                stable_counts[class_name] += 1

        return frame, stable_counts
