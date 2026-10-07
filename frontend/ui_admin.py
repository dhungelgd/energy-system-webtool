import streamlit as st
from streamlit.runtime import Runtime


def count_active_sessions():
    """Number of browser sessions (open tabs) connected to the app right now.

    Uses an internal Streamlit interface, so it is wrapped in try/except:
    if a future Streamlit version changes it, the app keeps working and
    simply shows no number.
    """

    try:
        return Runtime.instance()._session_mgr.num_active_sessions()
    except Exception:
        return None


@st.fragment(run_every=10)
def active_users_box():
    """Live counter, refreshed every 10 seconds without rerunning the app."""

    count = count_active_sessions()

    if count is None:
        st.caption("Active sessions: not available")
    else:
        st.metric("Active sessions", count)
        st.caption("Open browser tabs right now (includes yours). Updates every 10 s.")


def render_admin_panel():
    """Show the live counter in the sidebar, only for the link with ?admin=1.

    Participants use the normal link and see nothing.
    """

    if st.query_params.get("admin") != "1":
        return

    with st.sidebar:
        st.markdown("---")
        st.subheader("Admin")
        active_users_box()