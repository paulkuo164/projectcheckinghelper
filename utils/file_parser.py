import io


def extract_text(uploaded_file) -> str:
    """
    從上傳的 PDF 或 DOCX 檔案擷取純文字，並在每頁開頭插入頁碼標記。
    格式：=== 第 N 頁 ===
    """
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        return _extract_pdf(uploaded_file)
    elif filename.endswith(".docx"):
        return _extract_docx(uploaded_file)
    else:
        return uploaded_file.read().decode("utf-8", errors="ignore")


def _extract_pdf(uploaded_file) -> str:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text()
                if t and t.strip():
                    text_parts.append(f"=== 第 {i} 頁 ===\n{t.strip()}")
        return "\n\n".join(text_parts)
    except ImportError:
        return "[錯誤] 請安裝 pdfplumber：pip install pdfplumber"
    except Exception as e:
        return f"[PDF 解析失敗] {e}"


def _extract_docx(uploaded_file) -> str:
    """
    DOCX 沒有明確分頁，改用段落編號模擬位置，
    每 20 個段落視為一頁（可依實際情況調整）。
    """
    try:
        from docx import Document
        doc = Document(io.BytesIO(uploaded_file.read()))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        PAGE_SIZE = 20  # 每幾段視為一頁
        pages = []
        for page_num, start in enumerate(range(0, len(paragraphs), PAGE_SIZE), 1):
            chunk = paragraphs[start: start + PAGE_SIZE]
            pages.append(f"=== 第 {page_num} 頁（約第 {start+1}～{start+len(chunk)} 段）===\n" + "\n".join(chunk))
        return "\n\n".join(pages)
    except ImportError:
        return "[錯誤] 請安裝 python-docx：pip install python-docx"
    except Exception as e:
        return f"[DOCX 解析失敗] {e}"
