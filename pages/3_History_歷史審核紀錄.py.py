import streamlit as st
import json
import os
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="歷史審核紀錄", layout="wide")
st.title("📊 歷史審核紀錄")

record_path = "standards/history.json"

if not os.path.exists(record_path):
    st.info("尚無歷史紀錄。")
    st.stop()

with open(record_path, "r", encoding="utf-8") as f:
    records = json.load(f)

if not records:
    st.info("尚無歷史紀錄。")
    st.stop()

# ── 清單顯示 ──────────────────────────────────────────────────────────────
df = pd.DataFrame([{
    "審核時間": r.get("timestamp", "")[:16].replace("T", " "),
    "檔案名稱": r.get("filename", ""),
    "審核標準": r.get("standard", ""),
    "結論": r.get("verdict", ""),
    "審核摘要": r.get("summary", ""),
} for r in records])

col1, col2 = st.columns(2)
with col1:
    filter_standard = st.selectbox("篩選標準", ["全部"] + list(df["審核標準"].unique()))
with col2:
    filter_verdict = st.selectbox("篩選結論", ["全部"] + list(df["結論"].dropna().unique()))

mask = pd.Series([True] * len(df))
if filter_standard != "全部":
    mask &= df["審核標準"] == filter_standard
if filter_verdict != "全部":
    mask &= df["結論"] == filter_verdict

filtered_df      = df[mask].reset_index(drop=True)
filtered_records = [r for r, m in zip(records, mask) if m]

st.markdown(f"共 **{len(filtered_df)}** 筆紀錄")
st.dataframe(filtered_df, use_container_width=True, hide_index=True)

# ── 匯出 Excel ────────────────────────────────────────────────────────────
buf = BytesIO()
filtered_df.to_excel(buf, index=False, engine="openpyxl")
buf.seek(0)
st.download_button(
    "⬇️ 匯出 Excel",
    data=buf,
    file_name="審核紀錄.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.markdown("---")

# ── 查看詳細結果 ──────────────────────────────────────────────────────────
st.subheader("查看詳細審核結果")

if not filtered_records:
    st.info("無符合條件的紀錄。")
    st.stop()

options = [
    f"{r.get('timestamp','')[:16].replace('T',' ')}　{r.get('filename','')}"
    for r in filtered_records
]
selected_idx = st.selectbox("選擇紀錄", range(len(options)), format_func=lambda i: options[i])
record = filtered_records[selected_idx]

verdict = record.get("verdict", "")
summary = record.get("summary", "")
verdict_icon = {"通過": "✅", "待補件": "⚠️", "不通過": "❌"}.get(verdict, "📋")

st.markdown(f"### {verdict_icon} 審核結論：{verdict}")
st.info(summary)

items = record.get("items", [])
if not items:
    st.warning("此筆紀錄未保存詳細審查內容（為舊版紀錄）。")
    st.stop()

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
    cited    = item.get("regulations_cited", [])

    with st.expander(
        f"{icon} {item.get('criterion','—')}　{status}　（{len(issues)} 個問題・{len(conform)} 個符合依據）",
        expanded=(status in ("不符合", "部分符合")),
    ):
        if cited:
            st.caption("📎 引用規範：" + "　".join(f"`{c}`" for c in cited))

        summary_text = item.get("summary")
        if summary_text:
            st.markdown(f"**審查意見：** {summary_text}")
            st.markdown("---")

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

        suggestion = item.get("suggestion")
        if suggestion:
            st.info(f"💡 改善建議：{suggestion}")

for group in [fail_items, part_items, unk_items, ok_items]:
    for item in group:
        render_item(item)

missing_list = record.get("missing_items", [])
if missing_list:
    st.markdown("---")
    st.subheader("📌 整體待補件清單")
    for i, m in enumerate(missing_list, 1):
        st.write(f"{i}. {m}")
