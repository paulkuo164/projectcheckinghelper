import streamlit as st
import json
import os
import pandas as pd

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

df = pd.DataFrame(records)
df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")

df = df.rename(columns={
    "timestamp": "審核時間",
    "filename": "檔案名稱",
    "standard": "審核標準",
    "verdict": "結論",
    "summary": "審核摘要",
})

# 篩選
col1, col2 = st.columns(2)
with col1:
    filter_standard = st.selectbox("篩選標準", ["全部"] + list(df["審核標準"].unique()))
with col2:
    filter_verdict = st.selectbox("篩選結論", ["全部"] + list(df["結論"].dropna().unique()))

filtered = df.copy()
if filter_standard != "全部":
    filtered = filtered[filtered["審核標準"] == filter_standard]
if filter_verdict != "全部":
    filtered = filtered[filtered["結論"] == filter_verdict]

st.markdown(f"共 **{len(filtered)}** 筆紀錄")

display_cols = [c for c in ["審核時間", "檔案名稱", "審核標準", "結論", "審核摘要"] if c in filtered.columns]
st.dataframe(
    filtered[display_cols],
    use_container_width=True,
    hide_index=True,
)

csv = filtered.to_csv(index=False, encoding="utf-8-sig")
st.download_button("⬇️ 匯出 CSV", data=csv, file_name="審核紀錄.csv", mime="text/csv")
