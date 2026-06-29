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
    透過 Gemini File API 上傳檔案，等待狀態變成 ACTIVE 後回傳 file_uri。
    """
    import time

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
    file_uri  = file_info["file"]["uri"]
    file_name = file_info["file"]["name"]  # files/xxx

    # Step 3：等待檔案狀態變成 ACTIVE
    status_url = (
        f"https://generativelanguage.googleapis.com/v1beta/{file_name}"
        f"?key={api_key}"
    )
    for _ in range(20):  # 最多等 40 秒
        time.sleep(2)
        r = requests.get(status_url, timeout=15)
        if r.status_code == 200:
            state = r.json().get("state", "")
            if state == "ACTIVE":
                return file_uri
            elif state == "FAILED":
                raise ValueError("檔案處理失敗（File API state: FAILED）")
        # PROCESSING 狀態繼續等待

    return file_uri  # 等待超時仍回傳，讓後續嘗試


def _delete_gemini_file(file_uri: str, api_key: str):
    """審核完成後刪除已上傳的檔案。"""
    # file_uri 格式：https://generativelanguage.googleapis.com/v1beta/files/xxx
    file_name = file_uri.split("/v1beta/")[-1]  # files/xxx
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    try:
        requests.delete(url, timeout=15)
    except Exception:
        pass  # 刪除失敗不影響主流程


def _extract_toc(file_uri: str, file_mime: str, api_key: str) -> dict:
    """
    Step 1：讓 AI 讀取目錄頁，回傳章節名稱與頁碼範圍的對應表。
    """
    prompt = """請讀取這份文件的目錄頁，將所有章節名稱與對應頁碼範圍整理成 JSON。

輸出格式（僅輸出合法 JSON，不要有其他文字）：
{
  "chapters": [
    {
      "title": "<章節名稱，完整保留原文>",
      "page_start": <起始頁碼，整數>,
      "page_end": <結束頁碼，整數，若無法判斷則填 null>
    }
  ]
}

注意：
1. 只讀目錄頁，不要審查內文
2. 章節名稱完整保留原文，包含編號
3. 每個一級章節和二級章節都要列出
4. page_end 可由下一章節的 page_start - 1 推算
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
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 65536,
        },
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw)


def _match_chapter(criterion_name: str, chapters: list) -> dict | None:
    """
    將審核項目名稱對應到最相關的章節。
    用關鍵字比對，找不到則回傳 None（代表送全文審查）。
    """
    name = criterion_name.lower()
    # 移除編號前綴（如「1. 」「10. 」）
    import re
    name_clean = re.sub(r'^\d+[\.\s]+', '', name).strip()

    best = None
    best_score = 0
    for ch in chapters:
        title = ch.get("title", "").lower()
        title_clean = re.sub(r'^\d+[\.\s]+', '', title).strip()
        # 計算相似度：共同字元數
        common = sum(1 for c in name_clean if c in title_clean)
        if common > best_score:
            best_score = common
            best = ch

    # 相似度太低就不對應（送全文）
    if best_score < 2:
        return None
    return best


def _review_single_item(
    criterion: dict,
    chapter: dict | None,
    file_uri: str,
    file_mime: str,
    standard_name: str,
    api_key: str,
    extra_note: str = "",
) -> dict:
    """
    Step 2：針對單一審核項目，送對應章節內容進行精細審查。
    自動從向量資料庫查詢相關規範條文作為審查依據。
    """
    # RAG：查詢相關規範條文
    try:
        from utils.embeddings import search_regulations
        query = f"{criterion['name']} {criterion.get('description', '')}"
        reg_results = search_regulations(query, api_key, top_k=5)
        reg_context = ""
        if reg_results:
            reg_context = "\n\n## 相關規範條文（自動檢索）：\n"
            for r in reg_results:
                sim = round(r.get("similarity", 0) * 100, 1)
                reg_context += f"\n【{r['doc_name']}｜相關度 {sim}%】\n{r['content']}\n"
    except Exception:
        reg_context = ""

    if chapter and chapter.get("page_start"):
        page_info = f"請重點審查第 {chapter['page_start']} 頁"
        if chapter.get("page_end"):
            page_info += f" 至第 {chapter['page_end']} 頁"
        page_info += f"（對應章節：{chapter['title']}），若該範圍內找不到相關內容再擴大至全文。"
    else:
        page_info = "請審查全文中與此項目相關的所有內容。"

    extra_note_section = f"\n\n## 審查人員補充說明（請特別注意）：\n{extra_note}" if extra_note else ""

    prompt = f"""你是一位專業的計畫書審查委員，請針對以下單一審核項目進行精細審查。

## 審核標準：{standard_name}

## 審核項目：
【{criterion['name']}】
{criterion.get('description', '')}

## 審查範圍：
{page_info}
{reg_context}{extra_note_section}

---

## 輸出格式（僅輸出合法 JSON，不要有其他文字）：
{{
  "criterion": "{criterion['name']}",
  "status": "<符合 | 部分符合 | 不符合 | 無法判斷>",
  "summary": "<80~150字的詳細審查總結，具體說明判斷依據，如有引用規範請標注條號>",
  "evidence": [
    {{
      "page": "<第 N 頁>",
      "location": "<段落標題或關鍵字>",
      "description": "<具體說明此處內容如何符合或不符合，可引用上方規範條文對照>",
      "type": "<符合 | 問題>"
    }}
  ],
  "suggestion": "<具體改善建議，若完全符合則填 null>",
  "missing_items": ["<此項目的缺漏事項，如無則空陣列>"],
  "regulations_cited": ["<引用到的規範名稱，如 EM-1020、CNS 3090，如無則空陣列>"]
}}

注意：
1. evidence 至少填 1 筆，最多 3 筆
2. 若有提供相關規範條文，請在 summary 和 evidence 中具體對照引用
3. regulations_cited 填入實際有引用到的規範名稱
4. 頁碼請直接參考附件文件的實際頁碼
5. summary 限 100 字以內，description 每筆限 80 字以內
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

    for attempt in range(2):  # 最多重試一次
        try:
            resp = requests.post(url, json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()
            candidate = data["candidates"][0]
            if candidate.get("finishReason") == "MAX_TOKENS":
                raise ValueError(f"項目「{criterion['name']}」回傳被截斷")
            raw = candidate["content"]["parts"][0]["text"]
            return json.loads(raw)
        except requests.exceptions.Timeout:
            if attempt == 0:
                continue  # 重試一次
            raise Exception("請求逾時（已重試），請稍後再試或縮小審核範圍")
        except Exception:
            raise


def review_plan(file_bytes: bytes, file_mime: str, standard: dict, api_key: str) -> dict:
    """
    Chunk 審核流程：
    Step 1：AI 解析目錄，建立章節與頁碼對應表
    Step 2：每個審核項目各自對應章節，單獨精細審查
    """
    # 上傳檔案
    try:
        file_uri = _upload_file_to_gemini(file_bytes, file_mime, api_key)
    except Exception as e:
        return {"error": f"檔案上傳失敗：{e}"}

    # Step 1：解析目錄
    try:
        toc = _extract_toc(file_uri, file_mime, api_key)
        chapters = toc.get("chapters", [])
    except Exception:
        chapters = []  # 解析失敗就全部送全文審查

    criteria_all = standard.get("criteria", [])
    all_items = []
    all_missing = []

    # Step 2：逐項審查
    extra_note = standard.get("extra_note", "")

    for criterion in criteria_all:
        chapter = _match_chapter(criterion["name"], chapters)
        try:
            item = _review_single_item(
                criterion=criterion,
                chapter=chapter,
                file_uri=file_uri,
                file_mime=file_mime,
                standard_name=standard["name"],
                api_key=api_key,
                extra_note=extra_note,
            )
            missing = item.pop("missing_items", [])
            all_items.append(item)
            all_missing.extend(missing)
        except requests.exceptions.HTTPError as e:
            _delete_gemini_file(file_uri, api_key)
            return {"error": f"API 錯誤（項目：{criterion['name']}）：{e.response.status_code} {e.response.text[:200]}"}
        except Exception as e:
            _delete_gemini_file(file_uri, api_key)
            return {"error": f"審查失敗（項目：{criterion['name']}）：{e}"}

    _delete_gemini_file(file_uri, api_key)

    # 統計
    total         = len(all_items)
    ok_count      = sum(1 for it in all_items if it.get("status") == "符合")
    partial_count = sum(1 for it in all_items if it.get("status") == "部分符合")
    fail_count    = sum(1 for it in all_items if it.get("status") == "不符合")

    verdict = "通過" if (fail_count == 0 and partial_count == 0) else (
              "待補件" if fail_count == 0 else "不通過")

    seen = set()
    unique_missing = [m for m in all_missing if not (m in seen or seen.add(m))]

    return {
        "verdict": verdict,
        "summary": f"共 {total} 項審核項目｜符合 {ok_count} 項・部分符合 {partial_count} 項・不符合 {fail_count} 項",
        "toc_chapters": len(chapters),
        "items": all_items,
        "missing_items": unique_missing,
    }
