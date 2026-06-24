import json
import requests


def parse_standard_from_text(rule_text: str, api_key: str) -> dict:
    """
    將條文式規則文字（Word/PDF 擷取）解析成結構化審核標準 JSON。
    回傳格式與 standards.json 的單筆標準相同。
    """
    prompt = f"""你是一位熟悉台灣政府採購與工程審查的專業顧問。
請閱讀以下審核規則文件，將其中所有審核項目完整結構化成 JSON 格式，供 AI 系統逐條審查使用。

## 規則文件內容：
{rule_text[:30000]}

---

## 輸出格式（僅輸出合法 JSON，不要加任何說明或 markdown）：
{{
  "name": "<從文件推斷的標準名稱，例如：施工計畫書審核標準>",
  "description": "<一到兩句話說明此標準的適用範圍>",
  "criteria": [
    {{
      "name": "<審核項目名稱，盡量忠實保留原文，可超過10字>",
      "max_score": 10,
      "description": "<提供給 AI 審查員的判斷依據：說明此項目應審查什麼、通過條件、常見缺失，100~200字>"
    }}
  ]
}}

注意事項：
1. 每個項目 max_score 固定填 10，不需加總至 100
2. 項目數量：文件有幾條就列幾條，完整保留，不要合併或刪減
3. 若原文有子項目（例如 1.1、1.2），每個子項目獨立列為一筆 criteria
4. description 要具體說明判斷標準與通過條件，不要只重述項目名稱
5. 若文件中有明確評分或加權，請在 description 中標注
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"ok": True, "standard": json.loads(raw)}
    except requests.exceptions.HTTPError as e:
        return {"ok": False, "error": f"API 錯誤：{e.response.status_code} {e.response.text[:200]}"}
    except json.JSONDecodeError:
        return {"ok": False, "error": f"AI 回傳格式錯誤，無法解析 JSON。\n原始內容：{raw[:400]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def generate_reply_letter(
    incoming_text: str,
    plan_text: str,
    review_result: dict,
    org_info: dict,
    api_key: str,
) -> str:
    """
    依據來文內容、計畫書審核結果，產生正式公文回覆草稿（純文字）。
    org_info: {"sender": "發文機關", "recipient": "受文機關", "ref_no": "來文字號"}
    """
    verdict = review_result.get("verdict", "待確認")
    score = review_result.get("total_score", 0)
    max_score = review_result.get("max_score", 100)
    recommendation = review_result.get("recommendation", "")
    missing_items = review_result.get("missing_items", [])
    missing_text = "\n".join(f"  {i+1}. {m}" for i, m in enumerate(missing_items)) if missing_items else "  （無）"

    items_summary = "\n".join([
        f"  - {it['criterion']}：{it.get('score',0)}/{it.get('max_score',0)} 分　{'通過' if it.get('passed') else '未通過'}"
        for it in review_result.get("items", [])
    ])

    prompt = f"""你是一位負責撰寫政府機關公文的行政人員，請依下列資訊產生一份正式的公文回覆草稿。

【公文資訊】
- 發文機關（我方）：{org_info.get('sender', '○○機關')}
- 受文者（來函機關）：{org_info.get('recipient', '○○廠商')}
- 來文字號：{org_info.get('ref_no', '（請填入）')}

【來文重點摘要（系統擷取）】
{incoming_text[:2000]}

【計畫書審核結論】
- 審核結果：{verdict}
- 得分：{score} / {max_score} 分
- 各項評分摘要：
{items_summary}
- AI 建議：{recommendation}
- 待補件事項：
{missing_text}

【產生要求】
1. 格式依照台灣政府公文格式：主旨、說明、辦法（或請查照）三段式
2. 語氣正式、精簡，不使用口語
3. 若審核結論為「通過」：公文語氣表示同意，並告知後續作業事項
4. 若審核結論為「不通過」或「待補件」：公文語氣表示退件或要求補件，列出待補件清單
5. 直接輸出公文全文，不要加任何說明或前言
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except requests.exceptions.HTTPError as e:
        return f"[公文產生失敗] API 錯誤：{e.response.status_code} {e.response.text[:200]}"
    except Exception as e:
        return f"[公文產生失敗] {e}"


def review_plan(doc_text: str, standard: dict, api_key: str) -> dict:
    """
    呼叫 Gemini API，依據審核標準對計畫書文字進行審核。
    輸出：每個審核項目的問題條列（頁碼 + 問題描述），選填分數。
    支援大量審核項目：每批最多 15 項，分批送審後合併結果。
    """
    criteria_all = standard.get("criteria", [])
    BATCH_SIZE = 15

    all_items = []
    all_missing = []

    for batch_start in range(0, len(criteria_all), BATCH_SIZE):
        batch = criteria_all[batch_start: batch_start + BATCH_SIZE]
        criteria_text = "\n".join([
            f"- 【{c['name']}】：{c.get('description', '')}"
            for c in batch
        ])

        prompt = f"""你是一位專業的計畫書審查委員。請依照以下審核項目，逐條審查計畫書內容。

## 審核標準：{standard['name']}
{standard.get('description', '')}

### 本批次審核項目（共 {len(batch)} 項）：
{criteria_text}

---

## 計畫書內容（含頁碼標記）：
{doc_text[:20000]}

---

## 輸出格式（僅輸出合法 JSON，不要有其他文字）：
{{
  "items": [
    {{
      "criterion": "<審核項目名稱，與上方完全一致>",
      "status": "<符合 | 部分符合 | 不符合 | 無法判斷>",
      "score": <選填，整數，若不需評分請填 null>,
      "max_score": <該項滿分，若不需評分請填 null>,
      "issues": [
        {{
          "page": "<第 N 頁，若無法對應頁碼則填「全文」>",
          "location": "<段落標題或關鍵字，幫助定位位置>",
          "description": "<具體說明此處的問題或缺漏>"
        }}
      ],
      "suggestion": "<改善建議，若無問題則填 null>"
    }}
  ],
  "missing_items": ["<整體缺漏或需補件事項，如無則空陣列>"]
}}

注意：
1. items 數量必須與本批次審核項目數量完全一致（{len(batch)} 筆）
2. 若該項目完全符合規定，issues 填空陣列 []，suggestion 填 null
3. 頁碼請參考計畫書內容中的「=== 第 N 頁 ===」標記
4. 每個問題獨立列為一筆 issues，不要合併描述
"""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-1.5-flash:generateContent"
            f"?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            batch_result = json.loads(raw_text)
            all_items.extend(batch_result.get("items", []))
            all_missing.extend(batch_result.get("missing_items", []))
        except requests.exceptions.HTTPError as e:
            return {"error": f"API 錯誤（批次 {batch_start//BATCH_SIZE+1}）：{e.response.status_code} {e.response.text[:200]}"}
        except json.JSONDecodeError:
            return {"error": f"AI 回傳格式錯誤（批次 {batch_start//BATCH_SIZE+1}）。原始內容：{raw_text[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    # 統計
    total = len(all_items)
    ok_count = sum(1 for it in all_items if it.get("status") == "符合")
    partial_count = sum(1 for it in all_items if it.get("status") == "部分符合")
    fail_count = sum(1 for it in all_items if it.get("status") == "不符合")

    if fail_count == 0 and partial_count == 0:
        verdict = "通過"
    elif fail_count == 0:
        verdict = "待補件"
    else:
        verdict = "不通過"

    seen = set()
    unique_missing = [m for m in all_missing if not (m in seen or seen.add(m))]

    # 分數（若有填）
    scored_items = [it for it in all_items if it.get("score") is not None]
    total_score = sum(it.get("score", 0) for it in scored_items)
    max_score = sum(it.get("max_score", 0) for it in scored_items if it.get("max_score"))

    return {
        "verdict": verdict,
        "summary": f"共 {total} 項審核項目｜符合 {ok_count} 項・部分符合 {partial_count} 項・不符合 {fail_count} 項",
        "total_score": total_score if scored_items else None,
        "max_score": max_score if scored_items else None,
        "items": all_items,
        "missing_items": unique_missing,
    }

