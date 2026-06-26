import json
import os
import base64
import requests
import streamlit as st

# GitHub API 設定
# 從 Streamlit Secrets 或環境變數讀取
def _get_github_config():
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo  = st.secrets["GITHUB_REPO"]   # 格式：帳號/repo名稱
    except Exception:
        token = os.environ.get("GITHUB_TOKEN", "")
        repo  = os.environ.get("GITHUB_REPO", "")
    return token, repo

STANDARDS_FILE = "standards/standards.json"   # repo 內的路徑
LOCAL_PATH      = "standards/standards.json"   # 本機暫存路徑


# ── 讀取 ──────────────────────────────────────────────────────────────────

def load_standards() -> list:
    """
    優先從 GitHub 讀取最新版本；若無法連線則退回本機檔案。
    """
    token, repo = _get_github_config()

    if token and repo:
        result = _fetch_from_github(token, repo)
        if result is not None:
            # 同步寫入本機，供離線備援
            _write_local(result)
            return result

    # 退回本機
    return _read_local()


# ── 儲存 ──────────────────────────────────────────────────────────────────

def save_standards(standards: list) -> bool:
    """
    同時儲存到本機 + 推送至 GitHub。
    回傳 True 表示 GitHub 同步成功，False 表示僅存本機。
    """
    _write_local(standards)

    token, repo = _get_github_config()
    if token and repo:
        ok = _push_to_github(token, repo, standards)
        return ok

    return False


# ── GitHub 操作 ───────────────────────────────────────────────────────────

def _fetch_from_github(token: str, repo: str):
    """從 GitHub 取得 standards.json 內容，回傳 list 或 None。"""
    url = f"https://api.github.com/repos/{repo}/contents/{STANDARDS_FILE}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return []   # 檔案不存在視為空標準庫
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content)
    except Exception:
        return None


def _push_to_github(token: str, repo: str, standards: list) -> bool:
    """
    將 standards.json 推送至 GitHub（自動處理新增或更新）。
    """
    url = f"https://api.github.com/repos/{repo}/contents/{STANDARDS_FILE}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    content_b64 = base64.b64encode(
        json.dumps(standards, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")

    # 先取得現有檔案的 sha（更新時必須提供）
    sha = None
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
    except Exception:
        pass

    payload = {
        "message": "chore: update standards.json via Streamlit app",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception:
        return False


# ── 本機檔案操作 ──────────────────────────────────────────────────────────

def _read_local() -> list:
    if not os.path.exists(LOCAL_PATH):
        return []
    try:
        with open(LOCAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_local(standards: list):
    os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
    with open(LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(standards, f, ensure_ascii=False, indent=2)
