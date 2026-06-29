import streamlit as st
import json
import os
from utils.file_parser import extract_text
from utils.gemini_client import parse_standard_from_text
from utils.standards_loader import load_standards, save_standards

st.set_page_config(page_title="審核標準管理", layout="wide")
st.title("📂 審核標準管理")

standards = load_standards()

col_left, col_right = st.columns([1, 2])

# ── 左欄：標準清單 + 操作按鈕 ─────────────────────────────────────────────
with col_left:
    st.subheader("標準清單")
    if not standards:
        st.info("尚無審核標準，請從右側匯入或手動新增。")
    for i, s in enumerate(standards):
        total = sum(c.get("max_score", 0) for c in s.get("criteria", []))
        n_items = len(s.get("criteria", []))
        if st.button(
            f"📄 {s['name']}\n{n_items} 項目・滿分 {total}",
            key=f"sel_{i}", use_container_width=True
        ):
            st.session_state["editing_idx"] = i
            st.session_state.pop("import_preview", None)

    st.markdown("---")
    if st.button("📥 從文件匯入", use_container_width=True, type="primary",
                 help="上傳 Word / PDF 規則文件，AI 自動解析成審核標準"):
        st.session_state["editing_idx"] = "import"
        st.session_state.pop("import_preview", None)

    if st.button("➕ 手動新增", use_container_width=True):
        st.session_state["editing_idx"] = "new"
        st.session_state.pop("import_preview", None)

# ── 右欄：編輯區 ──────────────────────────────────────────────────────────
with col_right:
    idx = st.session_state.get("editing_idx")

    # ── 模式 A：從文件匯入 ──
    if idx == "import":
        st.subheader("📥 從規則文件匯入")
        st.caption("上傳 Word / PDF 格式的審核規則，AI 將自動解析成結構化標準，解析完成後可再手動調整。")

        api_key = st.session_state.get("gemini_api_key", "")
        if not api_key:
            api_key = st.text_input("Gemini API Key", type="password",
                                    help="此頁面操作需要 API Key")
            if api_key:
                st.session_state["gemini_api_key"] = api_key

        rule_file = st.file_uploader(
            "上傳審核規則文件（PDF / Word）",
            type=["pdf", "docx"],
            key="rule_uploader",
        )

        if rule_file and api_key:
            if st.button("🤖 AI 解析規則", type="primary"):
                with st.spinner("擷取文字中…"):
                    rule_text = extract_text(rule_file)
                with st.spinner("AI 解析規則文件中，請稍候…"):
                    result = parse_standard_from_text(rule_text, api_key)

                if result["ok"]:
                    st.session_state["import_preview"] = result["standard"]
                    st.success("解析完成！請確認下方內容，確認無誤後點擊「儲存為審核標準」。")
                else:
                    st.error(f"解析失敗：{result['error']}")

        # 顯示預覽並允許編輯後儲存
        preview = st.session_state.get("import_preview")
        if preview:
            st.markdown("---")
            st.subheader("解析結果預覽")

            p_name = st.text_input("標準名稱", value=preview.get("name", ""))
            p_desc = st.text_area("適用範圍說明", value=preview.get("description", ""), height=80)

            criteria = preview.get("criteria", [])
            total = sum(c.get("max_score", 0) for c in criteria)
            st.markdown(f"**審核項目**（共 {len(criteria)} 項）")

            edited_criteria = []
            for j, c in enumerate(criteria):
                is_required = c.get("required", j == 0)
                lock_icon = "🔒" if is_required else "📄"
                with st.expander(
                    f"{lock_icon} 項目 {j+1}：{c.get('name','未命名')}",
                    expanded=False
                ):
                    c_name     = st.text_input("項目名稱", value=c.get("name",""), key=f"pn_{j}")
                    c_desc     = st.text_area("審核重點說明", value=c.get("description",""),
                                              key=f"pd_{j}", height=100)
                    c_required = st.checkbox(
                        "🔒 設為必選", value=is_required, key=f"pr_{j}",
                        disabled=(j == 0)
                    )
                    keep = not st.checkbox("刪除此項目", key=f"pdel_{j}", disabled=(j == 0))
                    if keep:
                        edited_criteria.append({
                            "name": c_name,
                            "description": c_desc,
                            "required": True if j == 0 else c_required,
                        })

            new_total = sum(c["max_score"] for c in edited_criteria)
            st.caption(f"目前總分：**{new_total}** 分")

            if st.button("💾 儲存為審核標準", type="primary"):
                new_std = {"name": p_name, "description": p_desc, "criteria": edited_criteria}
                standards.append(new_std)
                save_ok = save_standards(standards)
                if save_ok:
                    st.success(f"「{p_name}」已儲存並同步至 GitHub ✅")
                else:
                    st.warning(f"「{p_name}」已存本機，但 GitHub 同步失敗，請確認 Secrets 設定。")
                st.session_state["editing_idx"] = None
                st.session_state.pop("import_preview", None)
                st.rerun()

        elif rule_file and not api_key:
            st.warning("請輸入 Gemini API Key 後再解析。")

    # ── 模式 B：手動新增 / 編輯 ──
    elif idx in ("new", *range(len(standards))):
        is_new = idx == "new"
        default = {"name": "", "description": "", "criteria": []} if is_new else standards[idx]

        st.subheader("手動新增" if is_new else f"編輯：{default['name']}")

        name        = st.text_input("標準名稱", value=default["name"])
        description = st.text_area("說明", value=default.get("description", ""), height=80)

        st.markdown("**審核項目**")
        criteria = list(default.get("criteria", []))
        updated_criteria = []

        for j, c in enumerate(criteria):
            is_required = c.get("required", j == 0)  # 第一項預設必選
            lock_icon = "🔒" if is_required else "📄"
            with st.expander(f"{lock_icon} 項目 {j+1}：{c.get('name','未命名')}", expanded=False):
                c_name = st.text_input("項目名稱", value=c.get("name",""), key=f"cn_{j}")
                c_desc = st.text_area("審核重點（AI 判斷依據）",
                                      value=c.get("description",""), key=f"cd_{j}", height=100)
                c_required = st.checkbox(
                    "🔒 設為必選（每次審核強制納入）",
                    value=is_required,
                    key=f"cr_{j}",
                    disabled=(j == 0),  # 第一項永遠鎖定
                    help="必選項目在審核頁面會以灰色鎖定，無法取消勾選"
                )
                remove = st.checkbox("🗑️ 刪除此項目", key=f"del_{j}", disabled=(j == 0))
                if not remove:
                    updated_criteria.append({
                        "name": c_name,
                        "description": c_desc,
                        "required": True if j == 0 else c_required,
                    })

        with st.expander("➕ 新增審核項目"):
            new_c_name     = st.text_input("項目名稱", key="new_crit_name")
            new_c_desc     = st.text_area("審核重點", key="new_crit_desc", height=80)
            new_c_required = st.checkbox("🔒 設為必選", key="new_crit_required", value=False)
            if st.button("加入項目") and new_c_name:
                updated_criteria.append({
                    "name": new_c_name,
                    "description": new_c_desc,
                    "required": new_c_required,
                })
                st.rerun()

        st.caption(f"共 {len(updated_criteria)} 個審核項目，其中 {sum(1 for c in updated_criteria if c.get('required'))} 個必選")

        col_save, col_del = st.columns([3, 1])
        with col_save:
            if st.button("💾 儲存", type="primary"):
                new_std = {"name": name, "description": description, "criteria": updated_criteria}
                if is_new:
                    standards.append(new_std)
                else:
                    standards[idx] = new_std
                save_ok = save_standards(standards)
                if save_ok:
                    st.success("儲存成功並同步至 GitHub ✅")
                else:
                    st.warning("已存本機，但 GitHub 同步失敗，請確認 Secrets 設定。")
                st.session_state["editing_idx"] = None
                st.rerun()
        with col_del:
            if not is_new and st.button("🗑️ 刪除"):
                standards.pop(idx)
                save_standards(standards)
                st.success("已刪除並同步至 GitHub ✅")
                st.session_state["editing_idx"] = None
                st.rerun()

    else:
        st.info("從左側選擇一個標準進行編輯，或點擊「從文件匯入」/「手動新增」。")
