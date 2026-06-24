# 計畫書 AI 自動審核系統

以 Streamlit + Gemini API 建構的計畫書自動審核工具，支援 PDF / Word 上傳，依自訂審核標準輸出結構化審核意見。

## 專案結構

```
plan_reviewer/
├── app.py                    # 首頁
├── pages/
│   ├── 1_審核計畫書.py        # 上傳文件 → AI 審核
│   ├── 2_審核標準管理.py      # 管理審核標準庫
│   └── 3_歷史審核紀錄.py      # 查閱歷史結果
├── utils/
│   ├── gemini_client.py      # Gemini API 呼叫
│   ├── file_parser.py        # PDF / DOCX 解析
│   └── standards_loader.py   # 標準庫 JSON 存取
├── standards/
│   └── standards.json        # 審核標準資料（可替換）
├── requirements.txt
└── .streamlit/config.toml
```

## 本機執行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署至 Streamlit Cloud

1. 將此目錄推送至 GitHub repository
2. 前往 [share.streamlit.io](https://share.streamlit.io)
3. 選擇你的 repo，Main file path 填入 `app.py`
4. 點擊 Deploy

> **API Key 安全性**：Streamlit Cloud 支援 Secrets 管理。
> 於 App Settings → Secrets 加入：
> ```toml
> GEMINI_API_KEY = "你的金鑰"
> ```
> 程式碼中可改用 `st.secrets["GEMINI_API_KEY"]` 取代手動輸入。

## 審核標準格式

`standards/standards.json` 為 JSON 陣列，每筆標準結構如下：

```json
{
  "name": "標準名稱",
  "description": "說明",
  "criteria": [
    {
      "name": "審核項目名稱",
      "max_score": 20,
      "description": "提供給 AI 的判斷依據說明"
    }
  ]
}
```

可直接編輯 JSON 檔案，或透過「審核標準管理」頁面操作。
