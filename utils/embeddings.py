import os
import json
import requests
import streamlit as st


# ── Supabase 連線 ─────────────────────────────────────────────────────────

def _get_supabase_config():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        if not url or not key:
            raise ValueError("SUPABASE_URL 或 SUPABASE_KEY 為空")
        return url.rstrip("/"), key
    except Exception as e:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError(
                f"找不到 Supabase 設定，請確認 Streamlit Secrets 已設定 SUPABASE_URL 和 SUPABASE_KEY。錯誤：{e}"
            )
        return url.rstrip("/"), key


def _supabase_request(method: str, path: str, body=None) -> dict:
    url, key = _get_supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    full_url = f"{url}/rest/v1/{path}"
    resp = requests.request(method, full_url, headers=headers,
                            json=body, timeout=30)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def _supabase_rpc(func_name: str, params: dict) -> list:
    url, key = _get_supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{url}/rest/v1/rpc/{func_name}",
        headers=headers,
        json=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json() if resp.text else []


# ── Gemini Embedding ──────────────────────────────────────────────────────

def get_embedding(text: str, api_key: str) -> list[float]:
    """
    用 gemini-embedding-001 將文字轉成 768 維向量（指定 outputDimensionality）。
    """
    url = (
        "https://generativelanguage.googleapis.com/v1/models/"
        f"gemini-embedding-001:embedContent?key={api_key}"
    )
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text[:8000]}]},
        "taskType": "RETRIEVAL_DOCUMENT",
        "outputDimensionality": 768,
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


# ── 文件切割 ─────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    將長文字切割成重疊的 chunks，依換行符號盡量在自然段落切割。
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += "\n" + para if current else para
        else:
            if current:
                chunks.append(current)
            # overlap：保留前一個 chunk 的後半段
            overlap_text = current[-overlap:] if len(current) > overlap else current
            current = overlap_text + "\n" + para if overlap_text else para

    if current:
        chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 20]


# ── 建庫：上傳規範文件 ────────────────────────────────────────────────────

def upload_regulation(
    doc_name: str,
    text: str,
    api_key: str,
    progress_callback=None,
) -> dict:
    """
    將規範文件切割成 chunks，向量化後存入 Supabase。
    回傳 {"ok": True, "chunks": N} 或 {"ok": False, "error": "..."}
    """
    # 先刪除同名舊資料（避免重複）
    url, key = _get_supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    requests.delete(
        f"{url}/rest/v1/regulations?doc_name=eq.{requests.utils.quote(doc_name)}",
        headers=headers,
        timeout=15,
    )

    chunks = chunk_text(text)
    total = len(chunks)
    inserted = 0

    for i, chunk in enumerate(chunks):
        try:
            embedding = get_embedding(chunk, api_key)

            # 確認維度
            if len(embedding) != 768:
                return {"ok": False, "error": f"向量維度不符：API 回傳 {len(embedding)} 維，資料表需要 768 維。請在 Supabase SQL Editor 重建資料表。"}

            row = {
                "doc_name": doc_name,
                "chunk_index": i,
                "content": chunk,
                "embedding": embedding,
                "metadata": {"chunk_total": total},
            }
            resp = _supabase_request("POST", "regulations", row)
            inserted += 1
            if progress_callback:
                progress_callback(i + 1, total)
        except Exception as e:
            return {"ok": False, "error": f"第 {i+1} 個 chunk 失敗：{e}｜向量長度：{len(embedding) if 'embedding' in dir() else '未知'}"}

    return {"ok": True, "chunks": inserted}


# ── 查詢：搜尋相關條文 ────────────────────────────────────────────────────

def search_regulations(
    query: str,
    api_key: str,
    top_k: int = 5,
    filter_docs: list[str] = None,
) -> list[dict]:
    """
    將查詢文字轉成向量，從 Supabase 找出最相關的條文。
    回傳 [{"doc_name": ..., "content": ..., "similarity": ...}, ...]
    """
    try:
        embedding = get_embedding(query, api_key)
        results = _supabase_rpc("match_regulations", {
            "query_embedding": embedding,
            "match_count": top_k,
            "filter_doc": None,
        })

        # 若有指定文件範圍則過濾
        if filter_docs:
            results = [r for r in results if r.get("doc_name") in filter_docs]

        return results
    except Exception as e:
        return []


# ── 列出已建庫的文件 ──────────────────────────────────────────────────────

def list_regulations() -> list[dict]:
    """
    列出 Supabase 中已建庫的所有規範文件，回傳 [{"doc_name": ..., "chunk_count": ...}]
    """
    try:
        url, key = _get_supabase_config()
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
        }
        resp = requests.get(
            f"{url}/rest/v1/regulations?select=doc_name&order=doc_name",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()
        # 統計每份文件的 chunk 數
        counts = {}
        for r in rows:
            n = r["doc_name"]
            counts[n] = counts.get(n, 0) + 1
        return [{"doc_name": k, "chunk_count": v} for k, v in sorted(counts.items())]
    except Exception:
        return []


# ── 刪除規範文件 ──────────────────────────────────────────────────────────

def delete_regulation(doc_name: str) -> bool:
    try:
        url, key = _get_supabase_config()
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
        }
        requests.delete(
            f"{url}/rest/v1/regulations?doc_name=eq.{requests.utils.quote(doc_name)}",
            headers=headers,
            timeout=15,
        )
        return True
    except Exception:
        return False
