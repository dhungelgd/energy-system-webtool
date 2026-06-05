import streamlit as st

def load_global_styles():

    st.markdown("""
    <style>
    
     /* MAIN BACKGROUND (correct target) */
    [data-testid="stAppViewContainer"] {
        background-color: #B3E2EB;
    }

    /* INNER CONTENT AREA */
    [data-testid="stMain"] {
        background-color: #EEF8F0;
    }

    /* OPTIONAL: sidebar */
    [data-testid="stSidebar"] {
        background-color: #F4F9FF;
    }
    
    /* -----------------------------
       GLOBAL APP STYLING
    ------------------------------*/

    /* App background tweaks */
    .stApp {
        background-color: #f3f5f7;
    }

    /* -----------------------------
       MULTISELECT COMPONENT
    ------------------------------*/

    /* input box */
    div[data-baseweb="select"] > div {
        min-height: 55px;
        font-size: 17px;
        border-radius: 12px;
        border: 2px solid #4CAF50;
        padding: 4px;
    }

    /* selected tags */
    span[data-baseweb="tag"] {
        background-color: #2E7D32 !important;
        color: white !important;
        font-size: 15px !important;
        border-radius: 8px !important;
        padding: 6px 10px !important;
    }

    /* dropdown menu items */
    div[data-baseweb="popover"] ul {
        font-size: 16px;
    }

    /* hover effect */
    div[data-baseweb="popover"] li:hover {
        background-color: #E8F5E9;
    }

    /* -----------------------------
       HEADERS
    ------------------------------*/

    h1, h2, h3 {
        font-weight: 600;
    }

    </style>
    """, unsafe_allow_html=True)