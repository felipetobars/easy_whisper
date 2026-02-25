# backend.py
import torch
import whisper
import numpy as np
import sounddevice as sd
import queue
from PySide6.QtCore import QThread, Signal

device = "cuda" if torch.cuda.is_available() else "cpu"
model = whisper.load_model("medium", device=device)

def get_input_devices() -> list[tuple[int, str]]:
    devices = sd.query_devices()
    return [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

class AudioRecorder(QThread):
    transcribed   = Signal(str)
    error         = Signal(str)
    finished      = Signal()
    volume_level  = Signal(int)   # <-- señal para nivel de volumen (0-100)

    def __init__(self, device_index: int, samplerate: int = 16000):
        super().__init__()
        self.samplerate   = samplerate
        self.device_index = device_index
        self.running      = True
        self.q            = queue.Queue()

    def callback(self, indata, frames, time, status):
        if status:
            print("Estado de grabación:", status)
        if self.running:
            # 1) Poner datos en la cola para cuando pare la grabación
            self.q.put(indata.copy())
            # 2) Calcular nivel de volumen (RMS) y mapear a 0–100
            rms = np.sqrt(np.mean(indata**2))
            # Normaliza un pico típico (ajusta según tu micro)
            level = min(int(rms * 5000), 100)
            self.volume_level.emit(level)

    def stop(self):
        self.running = False

    def run(self):
        try:
            with sd.InputStream(samplerate=self.samplerate,
                                channels=1,
                                dtype='float32',
                                device=self.device_index,
                                callback=self.callback):
                audio_frames = []
                while self.running:
                    try:
                        data = self.q.get(timeout=0.5)
                        audio_frames.append(data)
                    except queue.Empty:
                        continue

            audio = np.concatenate(audio_frames, axis=0).flatten()
            result = model.transcribe(audio, language="es")
            output = f"{result['text']}"
            self.transcribed.emit(output)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
