from ultralytics import YOLO
import cv2
import numpy as np

class ObjectDetector:
    def __init__(self, model_path="models/best.pt"):
        self.model = YOLO(model_path)

    def detect(self, frame):
        # panggil model dengan frame dan threshold
        results = self.model(frame, conf=0.15, verbose=False)
        detections = results[0].boxes

        for box in detections:
            xyxy = box.xyxy.cpu().numpy().squeeze().astype(int)
            conf = box.conf.item()
            cls = int(box.cls.item())
            label = f"{self.model.names[cls]} {conf:.2f}"

            # gambar kotak
            cv2.rectangle(frame, (xyxy[0], xyxy[1]),
                          (xyxy[2], xyxy[3]), (0, 255, 0), 2)
            cv2.putText(frame, label, (xyxy[0], xyxy[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return frame
