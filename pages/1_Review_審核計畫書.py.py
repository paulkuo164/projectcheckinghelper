import streamlit as st
import json
import os
import datetime
from utils.gemini_client import review_plan, generate_reply_letter
from utils.standards_loader import load_standards


# ── 輔助函式（需在呼叫前定義）────────────────────────────────────────────────
def _save_record(filename, standard, result):
    record_path = "standards/history.json"
    records = []
    if os.path.exists(record_path):
        with open(record_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    records.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "filename": filename,
        "standard": standard,
        "verdict": result.get("verdict", ""),
        "summary": result.get("summary", ""),
        "items": result.get("items", []),
        "missing_items": result.get("missing_items", []),
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

# ── 章節勾選 + 補充說明 ───────────────────────────────────────────────────
selected_criteria = []
if selected_standard and standards:
    standard_obj_preview = next((s for s in standards if s["name"] == selected_standard), None)
    if standard_obj_preview:
        criteria_all = standard_obj_preview.get("criteria", [])

        col_check, col_note = st.columns([1, 1])

        with col_check:
            st.subheader("📋 選擇審核章節")

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("全選", use_container_width=True):
                    for i, c in enumerate(criteria_all):
                        if not c.get("required", i == 0):
                            st.session_state[f"crit_check_{i}"] = True
            with btn_col2:
                if st.button("僅必選", use_container_width=True):
                    for i, c in enumerate(criteria_all):
                        if not c.get("required", i == 0):
                            st.session_state[f"crit_check_{i}"] = False

            st.markdown("")
            for i, c in enumerate(criteria_all):
                is_required = c.get("required", i == 0)
                if is_required:
                    st.checkbox(
                        f"🔒 {c['name']}",
                        value=True,
                        disabled=True,
                        key=f"crit_locked_{i}",
                        help="必選項目，已在審核標準中設定為強制納入"
                    )
                    selected_criteria.append(c)
                else:
                    checked = st.checkbox(
                        c["name"],
                        value=st.session_state.get(f"crit_check_{i}", True),
                        key=f"crit_check_{i}",
                    )
                    if checked:
                        selected_criteria.append(c)

            st.caption(f"已選 **{len(selected_criteria)}** / {len(criteria_all)} 項")

        with col_note:
            st.subheader("📝 補充說明")
            extra_note = st.text_area(
                "額外審查重點（選填）",
                height=220,
                placeholder="例如：\n- 本案為新北市安康段，請特別注意液化潛勢區施工規定\n- 廠商上次被要求補件的項目為品管人員資格，本次請加強審查\n- 本次計畫書版本為修正三版，請確認版次命名是否正確",
                help="這裡輸入的內容會附加在每個審核項目的 prompt 中，讓 AI 特別注意",
                key="extra_note",
                label_visibility="collapsed",
            )
            st.caption("此欄位會傳給所有審核項目的 AI，提醒特別注意事項。")

st.markdown("---")

# ── 執行按鈕 ──────────────────────────────────────────────────────────────
plan_ready   = "plan_bytes" in st.session_state
letter_ready = "letter_text" in st.session_state
can_run = bool(api_key and selected_standard and plan_ready and selected_criteria)

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
    elif not selected_criteria:
        st.warning("請至少選擇一個審核項目")
    elif not letter_ready:
        st.info("（未上傳來文，將略過公文回覆產生）")

# ── 審核執行 ──────────────────────────────────────────────────────────────
if run and can_run:
    standard_obj = next(s for s in standards if s["name"] == selected_standard)
    extra_note = st.session_state.get("extra_note", "").strip()

    standard_selected = {
        "name": standard_obj["name"],
        "description": standard_obj.get("description", ""),
        "criteria": selected_criteria,
        "extra_note": extra_note,
    }
    n_criteria = len(selected_criteria)
    hint = f"共 {n_criteria} 項，逐項精細審查"

    with st.spinner(f"Step 1：解析目錄章節中…"):
        result = review_plan(
            file_bytes=st.session_state["plan_bytes"],
            file_mime=st.session_state["plan_mime"],
            standard=standard_selected,
            api_key=api_key,
        )

    toc_count = result.get("toc_chapters", 0)
    if not result.get("error") and toc_count:
        st.toast(f"✅ 目錄解析完成，共 {toc_count} 個章節，開始逐項審查…")

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
    if result.get("toc_chapters"):
        st.caption(f"📑 已解析目錄 {result['toc_chapters']} 個章節，各項目依對應章節精細審查")
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
            evidence = item.get("evidence", [])
            issues   = [e for e in evidence if e.get("type") == "問題"]
            conform  = [e for e in evidence if e.get("type") == "符合"]

            with st.expander(
                f"{icon} {item.get('criterion','—')}　{status}　（{len(issues)} 個問題・{len(conform)} 個符合依據）",
                expanded=(status in ("不符合", "部分符合")),
            ):
                # 引用規範標籤
                cited = item.get("regulations_cited", [])
                if cited:
                    st.caption("📎 引用規範：" + "　".join(f"`{c}`" for c in cited))

                # 審查總結
                summary = item.get("summary")
                if summary:
                    st.markdown(f"**審查意見：** {summary}")
                    st.markdown("---")

                # 問題條列
                if issues:
                    st.markdown("**🔴 問題項目**")
                    for j, ev in enumerate(issues, 1):
                        page = ev.get("page", "—")
                        if str(page).strip().lstrip('-').isdigit():
                            page = f"第 {page} 頁"
                        loc  = ev.get("location", "")
                        desc = ev.get("description", "—")
                        loc_str = f"｜{loc}" if loc else ""
                        st.markdown(f"**問題 {j}｜{page}{loc_str}**")
                        st.warning(desc)

                # 符合依據
                if conform:
                    st.markdown("**🟢 符合依據**")
                    for j, ev in enumerate(conform, 1):
                        page = ev.get("page", "—")
                        if str(page).strip().lstrip('-').isdigit():
                            page = f"第 {page} 頁"
                        loc  = ev.get("location", "")
                        desc = ev.get("description", "—")
                        loc_str = f"｜{loc}" if loc else ""
                        st.markdown(f"**依據 {j}｜{page}{loc_str}**")
                        st.success(desc)

                # 改善建議
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
