# backend.py
import numpy as np
import sounddevice as sd
import queue
from faster_whisper import WhisperModel
from PySide6.QtCore import QThread, Signal

_model_cache = {}

def get_model(model_name: str) -> WhisperModel:
    if model_name not in _model_cache:
        _model_cache[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _model_cache[model_name]

def get_input_devices() -> list[tuple[int, str]]:
    devices = sd.query_devices()
    return [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

class AudioRecorder(QThread):
    transcribed   = Signal(str)
    error         = Signal(str)
    finished      = Signal()
    volume_level  = Signal(int)

    def __init__(self, device_index: int, samplerate: int = 16000, language: str = None, model_name: str = "small"):
        super().__init__()
        self.samplerate   = samplerate
        self.device_index = device_index
        self.language     = language
        self.model_name   = model_name
        self.running      = True
        self.q            = queue.Queue()

    def callback(self, indata, frames, time, status):
        if status:
            print("Estado de grabación:", status)
        if self.running:
            self.q.put(indata.copy())
            rms = np.sqrt(np.mean(indata**2))
            level = min(int(rms * 5000), 100)
            self.volume_level.emit(level)

    def stop(self):
        self.running = False

    def run(self):
        try:
            model = get_model(self.model_name)
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
            segments, _ = model.transcribe(audio, language=self.language)
            output = " ".join(segment.text for segment in segments).strip()
            self.transcribed.emit(output)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()