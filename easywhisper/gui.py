import os
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel,
    QTextEdit, QPushButton, QComboBox, QProgressBar, QApplication, QDialog, QHBoxLayout, QSpacerItem, QSizePolicy, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from backend import AudioRecorder, get_input_devices, TextCorrector, unload_llm, get_ollama_models, warm_up_llm
import pyautogui
import threading

class HelpDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("How to use the application")
        self.setMinimumWidth(500)
        self.setStyleSheet("font-size: 14px;")

        layout = QVBoxLayout(self)

        help_text = (
            "<h3>🎤 <b>Welcome to Easy Whisper!</b></h3>"
            "<h4>✅ <b>How to use:</b></h4>"
            "<p>1. 🔧 <b>Setup:</b> Select your microphone, transcription language, and Whisper model speed.</p>"
            "<p>2. 🎙️ <b>Record:</b> Press <b><u>Ctrl + Alt</u></b> to start/stop. The text appears in real-time as you speak.</p>"
            "<p>3. 🤖 <b>AI Correction:</b> Enable 'Enhance text' and choose any of your <b>local Ollama models</b> from the dropdown list to fix grammar and spelling.</p>"
            "<p>4. 📋 <b>Auto-Paste:</b> Once finished, the text is automatically copied and pasted into your active application window.</p>"
            "<p>5. 🤫 <b>Smart Chunking:</b> The app waits for natural pauses so your speech is never cut mid-sentence.</p>"
            "<h4>ℹ️ <i>Models are managed dynamically; switching models will swap them in your GPU memory automatically.</i></h4>"
        )

        help_label = QLabel(help_text)
        help_label.setAlignment(Qt.AlignLeft)
        help_label.setWordWrap(True)

        layout.addWidget(help_label)
        self.setLayout(layout)


class WhisperGUI(QMainWindow):
    toggle_hotkey = Signal()

    def __init__(self):
        super().__init__()

        self.toggle_hotkey.connect(self.toggle_recording)

        icon_path = os.path.join(os.path.dirname(__file__), "logo.png")
        icon = QIcon(icon_path)
        if icon.isNull():
            print("Error! Could not load the icon.")
        else:
            self.setWindowIcon(icon)

        self.setWindowTitle("Voice to Text Transcriber - Easy Whisper")
        self.setStyleSheet("font-size: 14px;")
        self.resize(900, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Microphone selector
        self.device_selector = QComboBox()
        for i, name in get_input_devices():
            self.device_selector.addItem(f"[{i}] {name}", userData=i)

        # Language selector
        self.language_selector = QComboBox()
        self.language_selector.addItem("Auto-detect", None)
        self.language_selector.addItem("Spanish", "es")
        self.language_selector.addItem("English", "en")
        self.language_selector.addItem("French", "fr")
        self.language_selector.addItem("German", "de")
        self.language_selector.addItem("Portuguese", "pt")
        self.language_selector.addItem("Italian", "it")
        self.language_selector.addItem("Chinese", "zh")
        self.language_selector.addItem("Japanese", "ja")

        # Model selector
        self.model_selector = QComboBox()
        self.model_selector.addItem("Small (Fast)", "small")
        self.model_selector.addItem("Medium (Slower, better multi-language)", "medium")

        # LLM enhancement option
        self.llm_checkbox = QCheckBox("Enhance text with IA (Ollama)")
        self.llm_checkbox.setChecked(True)
        self.llm_checkbox.setStyleSheet("font-weight: bold; color: #2c3e50;")

        # Ollama model selector
        self.ollama_model_selector = QComboBox()
        models = get_ollama_models()
        for m in models:
            self.ollama_model_selector.addItem(m)
        self.ollama_model_selector.currentTextChanged.connect(self.change_ollama_model)
        self.current_ollama_model = self.ollama_model_selector.currentText()

        # Sound intensity bar
        self.intensity_bar = QProgressBar()
        self.intensity_bar.setRange(0, 100)
        self.intensity_bar.setTextVisible(False)

        # Timer
        self.timer_label = QLabel("⏱️ Time: 0:00", alignment=Qt.AlignCenter)

        # Status
        self.info_label = QLabel("Using: CPU (transcribing)", alignment=Qt.AlignCenter)

        # Text output
        self.text_output = QTextEdit(readOnly=True)
        self.text_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.text_output.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_output.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Buttons
        self.record_button = QPushButton("🎙️ Start recording")
        self.record_button.clicked.connect(self.toggle_recording)

        self.help_button = QPushButton("?")
        self.help_button.clicked.connect(self.show_help)

        self.hotkey_label = QLabel("Use <b>Ctrl+Alt</b> to start and stop recording.", alignment=Qt.AlignCenter)

        # Layout
        layout.addWidget(QLabel("Select microphone:"))
        layout.addWidget(self.device_selector)
        layout.addWidget(QLabel("Select language:"))
        layout.addWidget(self.language_selector)
        layout.addWidget(QLabel("Select model:"))
        layout.addWidget(self.model_selector)
        layout.addWidget(self.llm_checkbox)
        layout.addWidget(QLabel("Select Ollama Model:"))
        layout.addWidget(self.ollama_model_selector)
        layout.addWidget(self.intensity_bar)
        layout.addWidget(self.timer_label)
        layout.addWidget(self.record_button)
        layout.addWidget(self.hotkey_label)
        layout.addWidget(self.info_label)
        layout.addWidget(self.text_output)

        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addItem(spacer)
        layout.addWidget(self.help_button, alignment=Qt.AlignRight)

        self.thread = None
        self.corrector = None # Initialize to avoid NameError or premature collection
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.start_time = None
        self.is_recording = False

    def closeEvent(self, event):
        """Ensure threads stop when closing the window"""
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        if self.corrector and self.corrector.isRunning():
            self.corrector.wait()
        
        # Free the GPU by unloading the LLM from Ollama
        unload_llm(self.current_ollama_model)
        event.accept()

    def change_ollama_model(self, new_model):
        if not new_model or new_model == self.current_ollama_model:
            return
        
        # Unload the old model from GPU
        old_model = self.current_ollama_model
        threading.Thread(target=unload_llm, args=(old_model,), daemon=True).start()
        
        # Update current model
        self.current_ollama_model = new_model
        
        # Warm up the new model in background
        self.info_label.setText(f"🔄 Switching to {new_model}...")
        threading.Thread(target=warm_up_llm, args=(new_model,), daemon=True).start()

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        # Stop and wait for old thread if it exists to avoid signal collisions
        if self.thread and self.thread.isRunning():
            self.thread.disconnect()
            self.thread.stop()
            self.thread.wait()

        self.text_output.clear()
        self.timer_label.setText("⏱️ Time: 0:00")
        self.is_recording = True
        self.full_text = ""

        idx = self.device_selector.currentData()
        lang = self.language_selector.currentData()
        model_name = self.model_selector.currentData()
        self.thread = AudioRecorder(device_index=idx, language=lang, model_name=model_name)
        self.thread.chunk_transcribed.connect(self.handle_chunk)
        self.thread.error.connect(self.show_error)
        self.thread.recorder_finished.connect(self.on_finished)
        self.thread.volume_level.connect(self.update_intensity)

        self.record_button.setText("🛑 Stop recording")
        self.record_button.setEnabled(True)
        self.info_label.setText("🎙️ Recording and transcribing...")

        self.start_time = time.time()
        self.timer.start(100)
        self.thread.start()

    def stop_recording(self):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.timer.stop()
            self.record_button.setEnabled(False)
            self.info_label.setText("⏳ Finishing transcription...")

    def update_intensity(self, level: int):
        self.intensity_bar.setValue(level)

    def update_timer(self):
        if self.start_time:
            elapsed = time.time() - self.start_time
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            t = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            self.timer_label.setText(f"⏱️ Time: {t}")

    def handle_chunk(self, text: str):
        if self.full_text:
            self.full_text += " " + text
        else:
            self.full_text = text
        self.text_output.setPlainText(self.full_text)
        # Scroll to bottom
        self.text_output.verticalScrollBar().setValue(self.text_output.verticalScrollBar().maximum())

    def show_error(self, msg: str):
        self.text_output.setText(f"❌ Error: {msg}")
        self.info_label.setText("An error occurred.")

    def on_finished(self):
        self.is_recording = False
        self.record_button.setText("🎙️ Start recording")
        self.record_button.setEnabled(False) # Disable while LLM or pasting are working
        
        # Wait for recording thread to stop to avoid QThread errors
        if self.thread:
            self.thread.wait()

        if hasattr(self, 'full_text') and self.full_text.strip():
            # If checkbox is checked, enhance with LLM
            if self.llm_checkbox.isChecked():
                self.info_label.setText("✨ Enhancing text with IA (Ollama)...")
                
                # Cleanup previous corrector if it exists
                if self.corrector and self.corrector.isRunning():
                    self.corrector.wait()

                # Get selected language name for the prompt
                current_lang_text = self.language_selector.currentText()
                if self.language_selector.currentIndex() == 0: # Auto-detect
                    current_lang_text = "Auto-detect"

                self.corrector = TextCorrector(self.full_text, model_name=self.current_ollama_model, language=current_lang_text)
                self.corrector.corrected.connect(self.apply_correction)
                self.corrector.error.connect(self.show_error)
                self.corrector.correction_finished.connect(self.finalize_process)
                self.corrector.start()
            else:
                # If not checked, use text as is
                self.apply_correction(self.full_text)
                self.finalize_process()
        else:
            self.finalize_process()

    def apply_correction(self, corrected_text: str):
        self.full_text = corrected_text
        self.text_output.setPlainText(corrected_text)
        self.info_label.setText("✅ Text corrected and copied.")
        QApplication.clipboard().setText(corrected_text)
        # Paste the corrected text
        QTimer.singleShot(500, lambda: pyautogui.hotkey('ctrl', 'v'))

    def finalize_process(self):
        self.record_button.setEnabled(True)
        if "Enhancing" in self.info_label.text():
             self.info_label.setText("✅ Process completed.")

    def show_help(self):
        help_dialog = HelpDialog()
        help_dialog.exec()