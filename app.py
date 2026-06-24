import streamlit as st

st.set_page_config(
    page_title="計畫書AI審核系統",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("📋 計畫書審核系統")
st.sidebar.markdown("---")
st.sidebar.markdown("""
**功能選單**
- 🔍 上傳並審核計畫書
- 📂 審核標準管理
- 📊 歷史審核紀錄
""")

st.title("計畫書 AI 自動審核系統")
st.markdown("請使用左側選單選擇功能，或直接前往 **審核計畫書** 頁面開始作業。")

col1, col2, col3 = st.columns(3)
with col1:
    st.info("#### 🔍 審核計畫書\n上傳 PDF / Word 檔案，由 AI 自動比對審核標準並輸出審核意見。")
with col2:
    st.info("#### 📂 審核標準管理\n管理審核標準庫，可上傳、編輯各類計畫書的評分項目與配分。")
with col3:
    st.info("#### 📊 歷史紀錄\n查閱過去審核結果，支援篩選與匯出 Excel。")
