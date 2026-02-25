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
    chunk_transcribed = Signal(str)
    error             = Signal(str)
    finished          = Signal()
    volume_level      = Signal(int)

    def __init__(self, device_index: int, samplerate: int = 16000, language: str = None, model_name: str = "small", chunk_duration: int = 15):
        super().__init__()
        self.samplerate   = samplerate
        self.device_index = device_index
        self.language     = language
        self.model_name   = model_name
        self.running      = True
        self.q            = queue.Queue()
        self.chunk_duration = chunk_duration
        self.chunk_samples = chunk_duration * samplerate

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
                
                audio_buffer = []
                current_samples = 0
                
                # Loop while running or while there's still data in the queue
                while self.running or not self.q.empty():
                    try:
                        # Get all available data from queue to process as a batch
                        while not self.q.empty():
                            data = self.q.get_nowait()
                            audio_buffer.append(data)
                            current_samples += len(data)

                        # If we have reached 15s, wait for a natural pause (silence) to avoid cutting words
                        if current_samples >= self.chunk_samples:
                            # Check if current chunk is "silent" (low energy)
                            # We look at the last part of audio_buffer to see if the user is pausing
                            last_data = audio_buffer[-1]
                            rms = np.sqrt(np.mean(last_data**2))
                            
                            # If it's quiet enough OR we have too much accumulated (30s max), transcribe
                            if rms < 0.005 or current_samples > self.chunk_samples * 2:
                                self._transcribe_chunk(model, audio_buffer)
                                audio_buffer = []
                                current_samples = 0
                        
                        # Wait a bit if we are still running but queue is empty
                        if self.running:
                            self.msleep(100)
                            
                    except queue.Empty:
                        pass
                    except Exception as e:
                        print(f"Error en bucle de audio: {e}")

                # Final chunk if there is any remaining audio
                if audio_buffer:
                    self._transcribe_chunk(model, audio_buffer)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def _transcribe_chunk(self, model, frames):
        if not frames:
            return ""
        # Concatenate and flatten audio
        audio = np.concatenate(frames, axis=0).flatten()
        # transcribe with VAD filter to reduce hallucinations/repetitions in silence
        segments, _ = model.transcribe(audio, language=self.language, vad_filter=True)
        text = " ".join(segment.text for segment in segments).strip()
        if text:
            self.chunk_transcribed.emit(text)
        return text