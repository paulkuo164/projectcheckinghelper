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
df["得分率"] = (df["score"] / df["max_score"] * 100).round(1).astype(str) + "%"
df = df.rename(columns={
    "timestamp": "審核時間",
    "filename": "檔案名稱",
    "standard": "審核標準",
    "score": "得分",
    "max_score": "滿分",
    "verdict": "結論",
    "recommendation": "AI建議",
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
st.dataframe(
    filtered[["審核時間", "檔案名稱", "審核標準", "得分", "滿分", "得分率", "結論"]],
    use_container_width=True,
    hide_index=True,
)

# 匯出
csv = filtered.to_csv(index=False, encoding="utf-8-sig")
st.download_button("⬇️ 匯出 CSV", data=csv, file_name="審核紀錄.csv", mime="text/csv")
