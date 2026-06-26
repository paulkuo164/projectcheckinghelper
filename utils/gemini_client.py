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
        "gemini-2.5-flash:generateContent"
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
        "gemini-2.5-flash:generateContent"
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


def _upload_file_to_gemini(file_bytes: bytes, file_mime: str, api_key: str) -> str:
    """
    透過 Gemini File API 上傳檔案，回傳 file_uri。
    支援大型 PDF，不受 inline_data 大小限制。
    """
    import io

    # Step 1：取得上傳 URL
    start_url = (
        f"https://generativelanguage.googleapis.com/upload/v1beta/files"
        f"?key={api_key}&uploadType=resumable"
    )
    headers_init = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Type": file_mime,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        start_url,
        headers=headers_init,
        json={"file": {"display_name": "plan_document"}},
        timeout=30,
    )
    resp.raise_for_status()
    upload_url = resp.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise ValueError("無法取得 File API 上傳 URL")

    # Step 2：上傳檔案內容
    resp2 = requests.post(
        upload_url,
        headers={
            "Content-Type": file_mime,
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
        },
        data=file_bytes,
        timeout=120,
    )
    resp2.raise_for_status()
    file_info = resp2.json()
    return file_info["file"]["uri"]


def _delete_gemini_file(file_uri: str, api_key: str):
    """審核完成後刪除已上傳的檔案。"""
    # file_uri 格式：https://generativelanguage.googleapis.com/v1beta/files/xxx
    file_name = file_uri.split("/v1beta/")[-1]  # files/xxx
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    try:
        requests.delete(url, timeout=15)
    except Exception:
        pass  # 刪除失敗不影響主流程


def review_plan(file_bytes: bytes, file_mime: str, standard: dict, api_key: str) -> dict:
    """
    呼叫 Gemini API，透過 File API 上傳完整檔案後進行審核。
    支援 100+ 頁的大型文件，不受 inline_data 大小限制。
    支援大量審核項目：每批最多 15 項，分批送審後合併結果。
    """
    # 先上傳檔案取得 URI
    try:
        file_uri = _upload_file_to_gemini(file_bytes, file_mime, api_key)
    except Exception as e:
        return {"error": f"檔案上傳失敗：{e}"}

    criteria_all = standard.get("criteria", [])
    BATCH_SIZE = 5

    all_items = []
    all_missing = []

    for batch_start in range(0, len(criteria_all), BATCH_SIZE):
        batch = criteria_all[batch_start: batch_start + BATCH_SIZE]
        criteria_text = "\n".join([
            f"- 【{c['name']}】：{c.get('description', '')}"
            for c in batch
        ])

        prompt = f"""你是一位專業的計畫書審查委員。請依照以下審核項目，逐條審查附件計畫書的完整內容（包含所有頁面），並針對每個項目撰寫具體的審查意見。

## 審核標準：{standard['name']}
{standard.get('description', '')}

### 本批次審核項目（共 {len(batch)} 項）：
{criteria_text}

---

## 輸出格式（僅輸出合法 JSON，不要有其他文字）：
{{
  "items": [
    {{
      "criterion": "<審核項目名稱，與上方完全一致>",
      "status": "<符合 | 部分符合 | 不符合 | 無法判斷>",
      "score": null,
      "max_score": null,
      "summary": "<50~100字的審查總結，說明整體判斷依據，無論通過與否都必須填寫>",
      "evidence": [
        {{
          "page": "<第 N 頁，若無法對應頁碼則填「全文」>",
          "location": "<段落標題或關鍵字>",
          "description": "<具體說明此處的內容如何符合或不符合該審核項目，引用文件中的實際內容>",
          "type": "<符合 | 問題>"
        }}
      ],
      "suggestion": "<具體改善建議，若完全符合則填 null>"
    }}
  ],
  "missing_items": ["<整體缺漏或需補件事項，如無則空陣列>"]
}}

注意：
1. items 數量必須與本批次審核項目數量完全一致（{len(batch)} 筆）
2. 每個項目的 summary 必須填寫，100字以內
3. evidence 每項最多 3 筆，通過時 type 填「符合」，有問題時 type 填「問題」
4. 頁碼請直接參考附件文件的實際頁碼
5. description 每筆 50 字以內，精簡有力
"""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent"
            f"?key={api_key}"
        )
        payload = {
            "contents": [{
                "parts": [
                    {"file_data": {"mime_type": file_mime, "file_uri": file_uri}},
                    {"text": prompt},
                ]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "maxOutputTokens": 65536,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=180)
            resp.raise_for_status()
            data = resp.json()

            # 檢查是否因 token 超限被截斷
            candidate = data["candidates"][0]
            finish_reason = candidate.get("finishReason", "")
            if finish_reason == "MAX_TOKENS":
                _delete_gemini_file(file_uri, api_key)
                return {"error": f"AI 回傳被截斷（批次 {batch_start//BATCH_SIZE+1}），請減少每批審核項目數量或縮短審核說明。"}

            raw_text = candidate["content"]["parts"][0]["text"]
            batch_result = json.loads(raw_text)
            all_items.extend(batch_result.get("items", []))
            all_missing.extend(batch_result.get("missing_items", []))
        except requests.exceptions.HTTPError as e:
            _delete_gemini_file(file_uri, api_key)
            return {"error": f"API 錯誤（批次 {batch_start//BATCH_SIZE+1}）：{e.response.status_code} {e.response.text[:200]}"}
        except json.JSONDecodeError:
            _delete_gemini_file(file_uri, api_key)
            return {"error": f"AI 回傳格式錯誤（批次 {batch_start//BATCH_SIZE+1}）。原始內容：{raw_text[:300]}"}
        except Exception as e:
            _delete_gemini_file(file_uri, api_key)
            return {"error": str(e)}

    # 審核完成，刪除已上傳的檔案
    _delete_gemini_file(file_uri, api_key)

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
