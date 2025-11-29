from gui.app_gui import start_gui
from backend.config import is_frozen_exe
import os

if is_frozen_exe():
    os.environ['APP_ENV'] = 'production'
else:
    os.environ['APP_ENV'] = 'development'

def main():
    start_gui()

if __name__ == "__main__":
    main()
