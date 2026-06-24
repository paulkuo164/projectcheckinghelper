import io


def extract_text(uploaded_file) -> str:
    """
    從上傳的 PDF 或 DOCX 檔案擷取純文字。
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
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n".join(text_parts)
    except ImportError:
        return "[錯誤] 請安裝 pdfplumber：pip install pdfplumber"
    except Exception as e:
        return f"[PDF 解析失敗] {e}"


def _extract_docx(uploaded_file) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(uploaded_file.read()))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        return "[錯誤] 請安裝 python-docx：pip install python-docx"
    except Exception as e:
        return f"[DOCX 解析失敗] {e}"
