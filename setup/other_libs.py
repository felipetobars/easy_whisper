import os
try:
    import torch
    if torch.cuda.is_available():
        os.system('pip install git+https://github.com/openai/whisper.git')
    else:
        os.system('pip install -U openai-whisper')
    os.system('pip install pyside6')
    os.system('pip install sounddevice')
    os.system('pip install numpy')
    os.system('pip install pyautogui')
    os.system('pip install keyboard')
except:
    pass