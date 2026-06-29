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

    doc_name = st.text_input(
        "文件名稱",
        placeholder="例：EM-1020、CNS 3090、職業安全衛生法",
        help="這個名稱會顯示在審核結果的引用來源中"
    )

    uploaded = st.file_uploader(
        "選擇規範文件（PDF / Word）",
        type=["pdf", "docx"],
        key="reg_uploader",
    )

    if uploaded:
        st.caption(f"📄 {uploaded.name}　（{round(uploaded.size/1024)}KB）")

    chunk_size = st.slider(
        "切割大小（字元數）",
        min_value=200, max_value=1000, value=500, step=100,
        help="較小的 chunk 定位精確但條文可能被截斷；較大的 chunk 保留完整性但搜尋較模糊"
    )

    can_upload = bool(api_key and doc_name and uploaded)

    if st.button("🚀 開始建庫", type="primary", disabled=not can_upload):
        with st.spinner("擷取文字中…"):
            text = extract_text(uploaded)

        if not text or len(text) < 50:
            st.error("文件內容擷取失敗或內容過短，請確認檔案是否有文字內容。")
        else:
            st.info(f"擷取到 {len(text):,} 字元，開始切割並建立向量索引…")
            progress_bar = st.progress(0)
            status_text = st.empty()

            def on_progress(current, total):
                pct = current / total
                progress_bar.progress(pct)
                status_text.caption(f"處理中 {current}/{total} chunks…")

            result = upload_regulation(
                doc_name=doc_name,
                text=text,
                api_key=api_key,
                progress_callback=on_progress,
            )

            if result["ok"]:
                progress_bar.progress(1.0)
                st.success(f"✅「{doc_name}」建庫完成，共 {result['chunks']} 個條文 chunks！")
                st.rerun()
            else:
                st.error(f"建庫失敗：{result['error']}")

    if not api_key:
        st.warning("請輸入 Gemini API Key")
    elif not doc_name:
        st.warning("請填入文件名稱")
    elif not uploaded:
        st.warning("請上傳規範文件")
