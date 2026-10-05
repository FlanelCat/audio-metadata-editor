import sys

from PySide6.QtWidgets import QApplication

from audio_metadata_editor.ui.main_window import MainWindow
from audio_metadata_editor.ui.application_icon import load_application_icon


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(load_application_icon())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
    