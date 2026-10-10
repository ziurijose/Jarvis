"""Face samples and the face-lock model, shared by first-run setup and JARVIS's startup check."""
import os

import cv2
import numpy as np

FACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Face-Recognition')
SAMPLES_NEEDED = 10
USER_ID = 1  # the model holds one person; JARVIS checks the face against this id


def cascade_path(face_dir: str = FACE_DIR) -> str:
    return os.path.join(face_dir, 'haarcascade_frontalface_default.xml')


def model_path(face_dir: str = FACE_DIR) -> str:
    return os.path.join(face_dir, 'trainer', 'trainer.yml')


def samples_dir(face_dir: str = FACE_DIR) -> str:
    return os.path.join(face_dir, 'samples')


def load_detector(face_dir: str = FACE_DIR):
    return cv2.CascadeClassifier(cascade_path(face_dir))


def find_faces(detector, gray):
    """Face rectangles (x, y, w, h) in a grayscale frame, largest first.

    Anything smaller than a fifth of the frame height is ignored: the user sits close to
    the camera, and small detections are almost always background patterns, not faces.
    """
    side = max(80, int(min(gray.shape[:2]) * 0.2))
    faces = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(side, side))
    return sorted(faces, key=lambda f: f[2] * f[3], reverse=True)


def clear_samples(face_dir: str = FACE_DIR) -> None:
    """Remove earlier photos so a new person's samples never mix with someone else's."""
    folder = samples_dir(face_dir)
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        if name.startswith('face.') and name.endswith('.jpg'):
            os.remove(os.path.join(folder, name))


def save_sample(gray_face, number: int, face_dir: str = FACE_DIR) -> None:
    cv2.imwrite(os.path.join(samples_dir(face_dir), f'face.{USER_ID}.{number}.jpg'), gray_face)


def train(face_dir: str = FACE_DIR) -> int:
    """Train the face lock on the saved samples. Returns how many photos it learned from."""
    folder = samples_dir(face_dir)
    faces = []
    for name in sorted(os.listdir(folder)):
        if name.startswith(f'face.{USER_ID}.') and name.endswith('.jpg'):
            image = cv2.imread(os.path.join(folder, name), cv2.IMREAD_GRAYSCALE)
            if image is not None:
                faces.append(image)
    if not faces:
        return 0
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces, np.array([USER_ID] * len(faces)))
    os.makedirs(os.path.dirname(model_path(face_dir)), exist_ok=True)
    recognizer.write(model_path(face_dir))
    return len(faces)
