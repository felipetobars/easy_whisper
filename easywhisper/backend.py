# backend.py
import numpy as np
import sounddevice as sd
import queue
from faster_whisper import WhisperModel
from PySide6.QtCore import QThread, Signal
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

_model_cache = {}
_corrector_cache = {"chain": None}

def get_model(model_name: str) -> WhisperModel:
    if model_name not in _model_cache:
        _model_cache[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _model_cache[model_name]

def warm_up_whisper(model_name: str = "small"):
    """Pre-loads the Whisper model into memory at startup"""
    try:
        get_model(model_name)
        print(f"Whisper model ({model_name}) pre-loaded successfully.")
    except Exception as e:
        print(f"Warning: Could not pre-load Whisper model: {e}")

def get_ollama_models() -> list[str]:
    """Fetches the list of available models from local Ollama instance"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return [m["name"] for m in models]
    except Exception as e:
        print(f"Warning: Could not fetch Ollama models: {e}")
    return []

def get_corrector_chain(model_name: str):
    """Returns the persistent correction chain (Singleton per model)"""
    # If the model changed, clear the cache
    if _corrector_cache.get("model_name") != model_name:
        _corrector_cache["chain"] = None
        _corrector_cache["model_name"] = model_name

    if _corrector_cache["chain"] is None:
        llm = ChatOllama(model=model_name, temperature=0)
        template = PromptTemplate.from_template(
            "You are correcting transcribed speech. "
            "Fix ONLY obvious spelling, punctuation and grammar errors. "
            "Keep all words exactly as written, including slang, informal words and proper nouns. "
            "If unsure whether something is an error, leave it unchanged. "
            "Language: {language}\n"
            "Return ONLY the corrected text, nothing else.\n\n"
            "{input_text}"
        )
        _corrector_cache["chain"] = template | llm
    return _corrector_cache["chain"]

def warm_up_llm(model_name: str):
    """Loads the model into VRAM/RAM by sending an empty request"""
    if not model_name:
        return
    try:
        chain = get_corrector_chain(model_name)
        chain.invoke({"input_text": "", "language": "Auto-detect"})
        print(f"LLM model ({model_name}) pre-loaded successfully.")
    except Exception as e:
        print(f"Warning: Could not warm up LLM ({model_name}): {e}")

import requests

def unload_llm(model_name: str):
    """Tells Ollama to unload the model from VRAM/RAM immediately"""
    if not model_name:
        return
    try:
        payload = {
            "model": model_name,
            "keep_alive": 0
        }
        requests.post("http://localhost:11434/api/generate", json=payload, timeout=2)
        print(f"LLM ({model_name}) unloaded from GPU successfully.")
    except Exception as e:
        print(f"Warning: Could not unload LLM: {e}")

class TextCorrector(QThread):
    corrected = Signal(str)
    error = Signal(str)
    correction_finished = Signal()

    def __init__(self, text: str, model_name: str, language: str = "Auto-detect"):
        super().__init__()
        self.text = text
        self.model_name = model_name
        self.language = language

    def run(self):
        try:
            if not self.text.strip():
                self.corrected.emit("")
                return
            
            chain = get_corrector_chain(self.model_name)
            response = chain.invoke({
                "input_text": self.text,
                "language": self.language
            })
            self.corrected.emit(response.content.strip())
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.correction_finished.emit()

def get_input_devices() -> list[tuple[int, str]]:
    devices = sd.query_devices()
    return [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

class AudioRecorder(QThread):
    chunk_transcribed = Signal(str)
    error             = Signal(str)
    recorder_finished = Signal()
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
            print("Recording status:", status)
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
                        print(f"Error in audio loop: {e}")

                # Final chunk if there is any remaining audio
                if audio_buffer:
                    self._transcribe_chunk(model, audio_buffer)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.recorder_finished.emit()

    def _transcribe_chunk(self, model, frames):
        if not frames:
            return ""
        # Concatenate and flatten audio
        audio = np.concatenate(frames, axis=0).flatten()
        
        # Transcribe. If self.language is None, Whisper will detect it.
        # We capture 'info' to get the detected language.
        segments, info = model.transcribe(audio, language=self.language, vad_filter=True)
        
        # Lock the language after the first detection to avoid re-detection in next chunks.
        # This prevents losing the first few words when Whisper is in "Auto-detect" mode.
        if self.language is None and info is not None:
            self.language = info.language
            print(f"Language detected and locked: {self.language} (probability: {info.language_probability:.2f})")

        text = " ".join(segment.text for segment in segments).strip()
        if text:
            self.chunk_transcribed.emit(text)
        return text