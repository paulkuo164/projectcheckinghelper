import streamlit as st
import json
import os
import datetime
from utils.file_parser import extract_text
from utils.gemini_client import review_plan, generate_reply_letter
from utils.standards_loader import load_standards

st.set_page_config(page_title="審核計畫書", layout="wide")
st.title("🔍 審核計畫書")

# ── Sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("設定")
    api_key = st.text_input(
        "Gemini API Key", type="password",
        value=st.session_state.get("gemini_api_key", ""),
        help="輸入後暫存於本次 session"
    )
    if api_key:
        st.session_state["gemini_api_key"] = api_key

    st.markdown("---")
    standards = load_standards()
    standard_names = [s["name"] for s in standards]
    selected_standard = st.selectbox("審核標準", standard_names) if standard_names else None
    if not standard_names:
        st.warning("尚未建立審核標準，請先至「審核標準管理」新增。")

    st.markdown("---")
    st.subheader("公文機關資訊")
    org_sender    = st.text_input("發文機關（我方）", value="國家住宅及都市更新中心")
    org_recipient = st.text_input("受文者（廠商/機關）", placeholder="○○營造有限公司")
    org_ref_no    = st.text_input("來文字號", placeholder="例：工程字第1130001234號")

# ── 上傳區 ────────────────────────────────────────────────────────────────
col_upload_plan, col_upload_letter = st.columns(2)

with col_upload_plan:
    st.subheader("① 計畫書")
    plan_file = st.file_uploader(
        "上傳計畫書（PDF / Word）",
        type=["pdf", "docx"],
        key="plan_uploader",
        label_visibility="collapsed",
    )
    if plan_file:
        with st.expander("預覽擷取文字", expanded=False):
            with st.spinner("解析中..."):
                plan_text = extract_text(plan_file)
            st.session_state["plan_text"] = plan_text
            st.text_area("", plan_text[:2000] + ("…" if len(plan_text) > 2000 else ""),
                         height=160, disabled=True, label_visibility="collapsed")
    else:
        st.session_state.pop("plan_text", None)

with col_upload_letter:
    st.subheader("② 來文")
    letter_file = st.file_uploader(
        "上傳來文（PDF / Word）",
        type=["pdf", "docx"],
        key="letter_uploader",
        label_visibility="collapsed",
    )
    if letter_file:
        with st.expander("預覽擷取文字", expanded=False):
            with st.spinner("解析中..."):
                letter_text = extract_text(letter_file)
            st.session_state["letter_text"] = letter_text
            st.text_area("", letter_text[:2000] + ("…" if len(letter_text) > 2000 else ""),
                         height=160, disabled=True, label_visibility="collapsed")
    else:
        st.session_state.pop("letter_text", None)

st.markdown("---")

# ── 執行按鈕 ──────────────────────────────────────────────────────────────
plan_ready   = "plan_text" in st.session_state
letter_ready = "letter_text" in st.session_state
can_run = api_key and selected_standard and plan_ready

col_btn, col_hint = st.columns([1, 3])
with col_btn:
    run = st.button("🚀 開始 AI 審核", type="primary", disabled=not can_run)
with col_hint:
    if not api_key:
        st.warning("請先在左側輸入 Gemini API Key")
    elif not selected_standard:
        st.warning("請先選擇審核標準")
    elif not plan_ready:
        st.warning("請上傳計畫書")
    elif not letter_ready:
        st.info("（未上傳來文，將略過公文回覆產生）")

# ── 審核執行 ──────────────────────────────────────────────────────────────
if run and can_run:
    standard_obj = next(s for s in standards if s["name"] == selected_standard)
    n_criteria = len(standard_obj.get("criteria", []))
    n_batches = max(1, (n_criteria + 14) // 15)
    batch_hint = f"（共 {n_criteria} 項，分 {n_batches} 批次送審）" if n_batches > 1 else ""

    with st.spinner(f"AI 審核計畫書中{batch_hint}，請稍候…"):
        result = review_plan(
            doc_text=st.session_state["plan_text"],
            standard=standard_obj,
            api_key=api_key,
        )

    if result.get("error"):
        st.error(f"審核失敗：{result['error']}")
        st.stop()

    # 若有來文，同步產生公文回覆
    reply_letter = None
    if letter_ready:
        with st.spinner("產生公文回覆草稿中…"):
            reply_letter = generate_reply_letter(
                incoming_text=st.session_state["letter_text"],
                plan_text=st.session_state["plan_text"],
                review_result=result,
                org_info={
                    "sender": org_sender,
                    "recipient": org_recipient,
                    "ref_no": org_ref_no,
                },
                api_key=api_key,
            )

    st.session_state["review_result"]  = result
    st.session_state["reply_letter"]   = reply_letter
    st.session_state["review_filename"] = plan_file.name if plan_file else "—"
    st.session_state["review_standard"] = selected_standard
    _save_record(
        plan_file.name if plan_file else "—",
        selected_standard,
        result.get("total_score", 0),
        result.get("max_score", 100),
        result,
    )

# ── 結果顯示 ──────────────────────────────────────────────────────────────
result      = st.session_state.get("review_result")
reply_letter = st.session_state.get("reply_letter")

if result:
    st.success("審核完成！")

    # 總覽指標
    score     = result.get("total_score", 0)
    max_score = result.get("max_score", 100)
    verdict   = result.get("verdict", "待確認")
    pass_rate = round(score / max_score * 100, 1) if max_score else 0

    m1, m2, m3 = st.columns([1, 1, 2])
    with m1:
        st.metric("總分", f"{score} / {max_score}", delta=verdict)
    with m2:
        st.metric("得分率", f"{pass_rate}%")
    with m3:
        st.info(f"**AI 建議：** {result.get('recommendation', '—')}")

    st.markdown("---")

    # 分頁：審核細節 ／ 公文回覆
    tab_review, tab_letter = st.tabs(["📋 審核細節", "📨 公文回覆草稿"])

    with tab_review:
        st.subheader("各審核項目")
        for item in result.get("items", []):
            icon = "✅" if item.get("passed") else "❌"
            with st.expander(
                f"{icon} {item['criterion']}　{item.get('score',0)} / {item.get('max_score',0)} 分",
                expanded=not item.get("passed", True),
            ):
                st.write(item.get("comment", "—"))
                if item.get("missing"):
                    st.warning(f"缺漏：{item['missing']}")

        missing_list = result.get("missing_items", [])
        if missing_list:
            st.markdown("---")
            st.subheader("📌 待補件清單")
            for i, m in enumerate(missing_list, 1):
                st.write(f"{i}. {m}")

    with tab_letter:
        if reply_letter is None:
            st.info("未上傳來文，無法產生公文回覆。請上傳來文後重新執行審核。")
        elif reply_letter.startswith("[公文產生失敗]"):
            st.error(reply_letter)
        else:
            st.subheader("公文回覆草稿")
            st.caption("以下為 AI 產生草稿，請人工確認後再正式發文。")

            # 可編輯的文字區
            edited = st.text_area(
                "草稿內容（可直接編輯）",
                value=reply_letter,
                height=480,
                key="letter_editor",
            )

            col_copy, col_dl = st.columns(2)
            with col_copy:
                st.download_button(
                    "⬇️ 下載草稿 (.txt)",
                    data=edited.encode("utf-8"),
                    file_name="公文回覆草稿.txt",
                    mime="text/plain",
                )
            with col_dl:
                st.caption("建議複製後貼入公文系統進行排版。")


# ── 輔助函式 ──────────────────────────────────────────────────────────────
def _save_record(filename, standard, score, max_score, result):
    record_path = "standards/history.json"
    records = []
    if os.path.exists(record_path):
        with open(record_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    records.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "filename": filename,
        "standard": standard,
        "score": score,
        "max_score": max_score,
        "verdict": result.get("verdict", ""),
        "recommendation": result.get("recommendation", ""),
    })
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
