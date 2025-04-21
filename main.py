# main.py
import sys
import os
import threading
import keyboard
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from gui import WhisperGUI

def register_hotkey(gui: WhisperGUI):
    # Al presionar Ctrl+Alt se emite la señal toggle_hotkey
    keyboard.add_hotkey("ctrl+alt", gui.toggle_hotkey.emit)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    icon_path = os.path.join(os.path.dirname(__file__), "logo.ico")
    app.setWindowIcon(QIcon(icon_path))

    window = WhisperGUI()
    window.show()

    # Inicia el listener del atajo en un hilo aparte
    threading.Thread(target=register_hotkey, args=(window,), daemon=True).start()

    sys.exit(app.exec())
