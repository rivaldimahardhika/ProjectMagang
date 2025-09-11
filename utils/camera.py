import cv2

class Camera:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)

    def __del__(self):
        self.cap.release()

    def generate_frames(self):
        while True:
            succes, frame = self.cap.read()
            if not succes:
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Conten-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')