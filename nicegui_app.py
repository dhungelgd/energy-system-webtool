"""Start the NiceGUI interface:   python nicegui_app.py

The pages are registered when frontend_nicegui.app is imported. The server is
only started when this file is run directly.
"""

from frontend_nicegui.app import run_server

if __name__ in {"__main__", "__mp_main__"}:
    run_server()