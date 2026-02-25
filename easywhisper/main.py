# main.py
import sys
import os
#sys.stderr = open(os.devnull, 'w')
import threading
import keyboard
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from gui import WhisperGUI

def silent_handler(mode, context, message):
    if mode == QtMsgType.QtWarningMsg:
        return
    print(message, file=sys.__stderr__)

def register_hotkey(gui: WhisperGUI):
    keyboard.add_hotkey("ctrl+alt", gui.toggle_hotkey.emit)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    #qInstallMessageHandler(silent_handler)

    icon_path = os.path.join(os.path.dirname(__file__), "logo.png")
    app.setWindowIcon(QIcon(icon_path))

    window = WhisperGUI()
    window.show()

    threading.Thread(target=register_hotkey, args=(window,), daemon=True).start()

    sys.exit(app.exec())