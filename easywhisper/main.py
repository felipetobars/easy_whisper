# main.py
import sys
import os
# sys.stderr = open(os.devnull, 'w')
import threading
import keyboard
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from gui import WhisperGUI
from backend import warm_up_llm, warm_up_whisper

def silent_handler(mode, context, message):
    if mode == QtMsgType.QtWarningMsg:
        return
    print(message, file=sys.__stderr__)

def register_hotkey(gui: WhisperGUI):
    keyboard.add_hotkey("ctrl+alt", gui.toggle_hotkey.emit)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    qInstallMessageHandler(silent_handler)

    icon_path = os.path.join(os.path.dirname(__file__), "logo.png")
    app.setWindowIcon(QIcon(icon_path))

    window = WhisperGUI()
    window.show()

    threading.Thread(target=register_hotkey, args=(window,), daemon=True).start()
    
    # Pre-load the LLM and Whisper model in the background
    # We take the model currently selected in the GUI
    initial_llm = window.current_ollama_model
    if initial_llm:
        threading.Thread(target=warm_up_llm, args=(initial_llm,), daemon=True).start()
    
    threading.Thread(target=warm_up_whisper, args=("small",), daemon=True).start()

    sys.exit(app.exec())