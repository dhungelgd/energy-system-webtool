"""Entry point for Streamlit (local and Community Cloud): streamlit run streamlit_app.py

This file lives in the repository root, so Streamlit puts the root on the
import path and `backend` and `frontend` are found without any installation.
"""

import runpy

runpy.run_module("frontend.app", run_name="__main__")
