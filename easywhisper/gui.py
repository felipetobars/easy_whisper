import os
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel,
    QTextEdit, QPushButton, QComboBox, QProgressBar, QApplication, QDialog, QHBoxLayout, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from backend import AudioRecorder, get_input_devices
import pyautogui

class HelpDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cómo usar la aplicación")
        self.setMinimumWidth(500)
        self.setStyleSheet("font-size: 14px;")

        layout = QVBoxLayout(self)

        help_text = (
            "<h3>🎤 <b>¡Bienvenido a la aplicación de transcripción!</b></h3>"
            "<h4>✅ <b>Instrucciones de uso:</b></h4>"
            "<p>1. 🔧 <b>Selecciona tu micrófono</b> en la lista desplegable.</p>"
            "<p>2. 🎙️ Habla normalmente y presiona <b><u>Ctrl + Alt</u></b> para <b>comenzar o detener</b> la grabación.</p>"
            "<p>3. 📋 El texto transcrito se copiará automáticamente y se pegará en la aplicación que tengas activa.</p>"
            "<p>4. 🔵 La <b>barra azul</b> muestra la intensidad del sonido detectado (más alta = estás hablando).</p>"
            "<p>5. 🎛️ También puedes usar el botón de la interfaz para controlar manualmente la grabación.</p>"
            "<h4>ℹ️ La transcripción puede tardar unos segundos al terminar de hablar.</h4>"
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
            print("¡Error! No se pudo cargar el icono.")
        else:
            self.setWindowIcon(icon)

        self.setWindowTitle("Transcriptor de voz a texto - Easy Whisper")
        self.setStyleSheet("font-size: 14px;")
        self.resize(600, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Selector de micrófono
        self.device_selector = QComboBox()
        for i, name in get_input_devices():
            self.device_selector.addItem(f"[{i}] {name}", userData=i)

        # Selector de idioma
        self.language_selector = QComboBox()
        self.language_selector.addItem("Auto detectar", None)
        self.language_selector.addItem("Español", "es")
        self.language_selector.addItem("English", "en")
        self.language_selector.addItem("Français", "fr")
        self.language_selector.addItem("Deutsch", "de")
        self.language_selector.addItem("Português", "pt")
        self.language_selector.addItem("Italiano", "it")
        self.language_selector.addItem("中文", "zh")
        self.language_selector.addItem("日本語", "ja")

        # Selector de modelo
        self.model_selector = QComboBox()
        self.model_selector.addItem("Small (rápido)", "small")
        self.model_selector.addItem("Medium (lento, mejor multi idioma)", "medium")

        # Barra de intensidad de sonido
        self.intensity_bar = QProgressBar()
        self.intensity_bar.setRange(0, 100)
        self.intensity_bar.setTextVisible(False)

        # Temporizador
        self.timer_label = QLabel("⏱️ Tiempo: 0:00", alignment=Qt.AlignCenter)

        # Estado
        self.info_label = QLabel("Usando: CPU", alignment=Qt.AlignCenter)

        # Cuadro de texto
        self.text_output = QTextEdit(readOnly=True)
        self.text_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.text_output.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_output.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Botones
        self.record_button = QPushButton("🎙️ Iniciar grabación")
        self.record_button.clicked.connect(self.toggle_recording)

        self.help_button = QPushButton("?")
        self.help_button.clicked.connect(self.show_help)

        self.hotkey_label = QLabel("Usa <b>Ctrl+Alt</b> para iniciar y detener la grabación.", alignment=Qt.AlignCenter)

        # Layout
        layout.addWidget(QLabel("Selecciona el micrófono:"))
        layout.addWidget(self.device_selector)
        layout.addWidget(QLabel("Selecciona el idioma:"))
        layout.addWidget(self.language_selector)
        layout.addWidget(QLabel("Selecciona el modelo:"))
        layout.addWidget(self.model_selector)
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
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.start_time = None
        self.is_recording = False

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.text_output.clear()
        self.timer_label.setText("⏱️ Tiempo: 0:00")
        self.is_recording = True

        idx = self.device_selector.currentData()
        lang = self.language_selector.currentData()
        model_name = self.model_selector.currentData()
        self.thread = AudioRecorder(device_index=idx, language=lang, model_name=model_name)
        self.thread.transcribed.connect(self.show_result)
        self.thread.error.connect(self.show_error)
        self.thread.finished.connect(self.on_finished)
        self.thread.volume_level.connect(self.update_intensity)

        self.record_button.setText("🛑 Detener grabación")
        self.record_button.setEnabled(True)
        self.info_label.setText("🎙️ Grabando...")

        self.start_time = time.time()
        self.timer.start(100)
        self.thread.start()

    def stop_recording(self):
        if self.thread:
            self.thread.stop()
            self.timer.stop()
            self.record_button.setEnabled(False)
            self.info_label.setText("⏳ Procesando...")

    def update_intensity(self, level: int):
        self.intensity_bar.setValue(level)

    def update_timer(self):
        if self.start_time:
            elapsed = time.time() - self.start_time
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            t = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            self.timer_label.setText(f"⏱️ Tiempo: {t}")

    def show_result(self, text: str):
        self.text_output.setText(text)
        self.info_label.setText("✅ Transcripción completada.")
        QApplication.clipboard().setText(text)
        QTimer.singleShot(300, lambda: pyautogui.hotkey('ctrl', 'v'))

    def show_error(self, msg: str):
        self.text_output.setText(f"❌ Error: {msg}")
        self.info_label.setText("Ocurrió un error.")

    def on_finished(self):
        self.is_recording = False
        self.record_button.setText("🎙️ Iniciar grabación")
        self.record_button.setEnabled(True)
        self.info_label.setText("✅ Transcripción completada.")

    def show_help(self):
        help_dialog = HelpDialog()
        help_dialog.exec()