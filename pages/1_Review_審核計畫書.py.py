import streamlit as st
import json
import os
import datetime
from utils.gemini_client import review_plan, generate_reply_letter
from utils.standards_loader import load_standards


# ── 輔助函式（需在呼叫前定義）────────────────────────────────────────────────
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
        "summary": result.get("summary", ""),
    })
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

st.set_page_config(page_title="審核計畫書", layout="wide")
st.title("🔍 審核計畫書")

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("設定")
    api_key = st.text_input(
        "Gemini API Key", type="password",
        value=st.session_state.get("gemini_api_key", ""),
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
    org_recipient = st.text_input("受文者", placeholder="○○營造有限公司")
    org_ref_no    = st.text_input("來文字號", placeholder="工程字第1130001234號")

# ── 上傳區 ────────────────────────────────────────────────────────────────
col_plan, col_letter = st.columns(2)

with col_plan:
    st.subheader("① 計畫書")
    plan_file = st.file_uploader(
        "上傳計畫書（PDF / Word）",
        type=["pdf", "docx"],
        key="plan_uploader",
        label_visibility="collapsed",
    )
    if plan_file:
        st.caption(f"📄 {plan_file.name}　（{round(plan_file.size/1024)}KB）")
        plan_bytes = plan_file.read()
        plan_mime  = "application/pdf" if plan_file.name.lower().endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        st.session_state["plan_bytes"] = plan_bytes
        st.session_state["plan_mime"]  = plan_mime
        st.session_state["plan_name"]  = plan_file.name
    else:
        for k in ("plan_bytes", "plan_mime", "plan_name"):
            st.session_state.pop(k, None)

with col_letter:
    st.subheader("② 來文")
    letter_file = st.file_uploader(
        "上傳來文（PDF / Word）",
        type=["pdf", "docx"],
        key="letter_uploader",
        label_visibility="collapsed",
    )
    if letter_file:
        st.caption(f"📄 {letter_file.name}　（{round(letter_file.size/1024)}KB）")
        from utils.file_parser import extract_text
        letter_bytes = letter_file.read()
        # 來文仍需擷取文字供公文回覆使用
        import io
        letter_file.seek(0)
        letter_text = extract_text(letter_file)
        st.session_state["letter_text"] = letter_text
        st.session_state["letter_name"] = letter_file.name
    else:
        for k in ("letter_text", "letter_name"):
            st.session_state.pop(k, None)

st.markdown("---")

# ── 執行按鈕 ──────────────────────────────────────────────────────────────
plan_ready   = "plan_bytes" in st.session_state
letter_ready = "letter_text" in st.session_state
can_run = bool(api_key and selected_standard and plan_ready)

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
    n_batches  = max(1, (n_criteria + 14) // 15)
    hint = f"共 {n_criteria} 項，分 {n_batches} 批次送審" if n_batches > 1 else f"共 {n_criteria} 項"

    with st.spinner(f"AI 審核中（{hint}），請稍候…"):
        result = review_plan(
            file_bytes=st.session_state["plan_bytes"],
            file_mime=st.session_state["plan_mime"],
            standard=standard_obj,
            api_key=api_key,
        )

    if result.get("error"):
        st.error(f"審核失敗：{result['error']}")
        st.stop()

    reply_letter = None
    if letter_ready:
        with st.spinner("產生公文回覆草稿中…"):
            reply_letter = generate_reply_letter(
                incoming_text=st.session_state["letter_text"],
                plan_text="（已改用完整檔案審核，詳見審核結果）",
                review_result=result,
                org_info={"sender": org_sender, "recipient": org_recipient, "ref_no": org_ref_no},
                api_key=api_key,
            )

    st.session_state["review_result"] = result
    st.session_state["reply_letter"]  = reply_letter
    _save_record(
        st.session_state.get("plan_name", "—"),
        selected_standard,
        result.get("total_score"),
        result.get("max_score"),
        result,
    )

# ── 結果顯示 ──────────────────────────────────────────────────────────────
result       = st.session_state.get("review_result")
reply_letter = st.session_state.get("reply_letter")

if result:
    st.success("審核完成！")

    verdict = result.get("verdict", "待確認")
    summary = result.get("summary", "")
    verdict_icon = {"通過": "✅", "待補件": "⚠️", "不通過": "❌"}.get(verdict, "📋")

    st.markdown(f"### {verdict_icon} 審核結論：{verdict}")
    st.info(summary)

    if result.get("total_score") is not None:
        s, ms = result["total_score"], result["max_score"]
        st.caption(f"參考得分：{s} / {ms} 分（{round(s/ms*100,1) if ms else 0}%）")

    st.markdown("---")

    tab_review, tab_letter = st.tabs(["📋 審核細節", "📨 公文回覆草稿"])

    with tab_review:
        items = result.get("items", [])
        fail_items  = [it for it in items if it.get("status") == "不符合"]
        part_items  = [it for it in items if it.get("status") == "部分符合"]
        ok_items    = [it for it in items if it.get("status") == "符合"]
        unk_items   = [it for it in items if it.get("status") == "無法判斷"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("❌ 不符合", len(fail_items))
        c2.metric("⚠️ 部分符合", len(part_items))
        c3.metric("✅ 符合", len(ok_items))
        c4.metric("❓ 無法判斷", len(unk_items))
        st.markdown("---")

        def render_item(item):
            status = item.get("status", "—")
            icon   = {"符合": "✅", "部分符合": "⚠️", "不符合": "❌", "無法判斷": "❓"}.get(status, "📋")
            issues = item.get("issues", [])
            with st.expander(
                f"{icon} {item.get('criterion','—')}　{status}　（{len(issues)} 個問題）",
                expanded=(status in ("不符合", "部分符合")),
            ):
                if not issues:
                    st.success("此項目無問題，符合規定。")
                else:
                    for j, issue in enumerate(issues, 1):
                        page = issue.get("page", "—")
                        loc  = issue.get("location", "")
                        desc = issue.get("description", "—")
                        loc_str = f"｜{loc}" if loc else ""
                        st.markdown(f"**問題 {j}｜{page}{loc_str}**")
                        st.warning(desc)
                suggestion = item.get("suggestion")
                if suggestion:
                    st.info(f"💡 改善建議：{suggestion}")

        for group in [fail_items, part_items, unk_items, ok_items]:
            for item in group:
                render_item(item)

        missing_list = result.get("missing_items", [])
        if missing_list:
            st.markdown("---")
            st.subheader("📌 整體待補件清單")
            for i, m in enumerate(missing_list, 1):
                st.write(f"{i}. {m}")

    with tab_letter:
        if reply_letter is None:
            st.info("未上傳來文，無法產生公文回覆。請上傳來文後重新執行審核。")
        elif str(reply_letter).startswith("[公文產生失敗]"):
            st.error(reply_letter)
        else:
            st.subheader("公文回覆草稿")
            st.caption("以下為 AI 產生草稿，請人工確認後再正式發文。")
            edited = st.text_area("草稿內容（可直接編輯）", value=reply_letter, height=480, key="letter_editor")
            st.download_button("⬇️ 下載草稿 (.txt)", data=edited.encode("utf-8"),
                               file_name="公文回覆草稿.txt", mime="text/plain")
