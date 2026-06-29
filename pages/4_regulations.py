import os
import streamlit as st
from utils.file_parser import extract_text
from utils.embeddings import upload_regulation, list_regulations, delete_regulation

st.set_page_config(page_title="規範管理", layout="wide")
st.title("📚 規範文件管理")
st.caption("上傳規範文件後，系統會自動切割並建立向量索引，審核時自動引用相關條文。")

api_key = st.session_state.get("gemini_api_key", "")
if not api_key:
    api_key = st.text_input("Gemini API Key", type="password")
    if api_key:
        st.session_state["gemini_api_key"] = api_key

st.markdown("---")
col_left, col_right = st.columns([1, 1])

# ── 左欄：已建庫文件清單 ──────────────────────────────────────────────────
with col_left:
    st.subheader("已建庫規範")

    if st.button("🔄 重新整理", key="refresh"):
        st.rerun()

    docs = list_regulations()
    if not docs:
        st.info("尚未上傳任何規範文件。")
    else:
        for doc in docs:
            col_name, col_del = st.columns([3, 1])
            with col_name:
                st.markdown(f"📄 **{doc['doc_name']}**")
                st.caption(f"{doc['chunk_count']} 個條文 chunks")
            with col_del:
                if st.button("🗑️", key=f"del_{doc['doc_name']}",
                             help=f"刪除 {doc['doc_name']}"):
                    if delete_regulation(doc["doc_name"]):
                        st.success(f"已刪除 {doc['doc_name']}")
                        st.rerun()

# ── 右欄：上傳新規範 ──────────────────────────────────────────────────────
with col_right:
    st.subheader("上傳規範文件")

    uploaded_files = st.file_uploader(
        "選擇規範文件（PDF / Word，可一次選多個）",
        type=["pdf", "docx"],
        key="reg_uploader",
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.caption(f"已選 {len(uploaded_files)} 個檔案：")
        for f in uploaded_files:
            st.caption(f"　📄 {f.name}　（{round(f.size/1024)}KB）")

    chunk_size = st.slider(
        "切割大小（字元數）",
        min_value=200, max_value=1000, value=400, step=100,
        help="較小的 chunk 定位精確但條文可能被截斷；較大的 chunk 保留完整性但搜尋較模糊"
    )

    st.caption("💡 自動使用檔名（去除副檔名）作為規範名稱。")

    can_upload = bool(api_key and uploaded_files)

    if st.button("🚀 開始建庫", type="primary", disabled=not can_upload):
        for uploaded in uploaded_files:
            auto_name = os.path.splitext(uploaded.name)[0]
            st.markdown(f"**📄 處理：{auto_name}**")

            with st.spinner(f"擷取 {uploaded.name} 文字中…"):
                text = extract_text(uploaded)

            if not text or len(text) < 50:
                st.error(f"「{uploaded.name}」內容擷取失敗或過短，已跳過。")
                continue

            st.info(f"擷取到 {len(text):,} 字元，開始建立向量索引…")
            progress_bar = st.progress(0)
            status_text  = st.empty()

            def on_progress(current, total, bar=progress_bar, txt=status_text):
                bar.progress(current / total)
                txt.caption(f"處理中 {current}/{total} chunks…")

            result = upload_regulation(
                doc_name=auto_name,
                text=text,
                api_key=api_key,
                progress_callback=on_progress,
            )

            if result["ok"]:
                progress_bar.progress(1.0)
                st.success(f"✅「{auto_name}」建庫完成，共 {result['chunks']} 個條文 chunks！")
            else:
                st.error(f"「{auto_name}」建庫失敗：{result['error']}")

        st.rerun()

    if not api_key:
        st.warning("請輸入 Gemini API Key")
    elif not uploaded_files:
        st.warning("請選擇規範文件")
