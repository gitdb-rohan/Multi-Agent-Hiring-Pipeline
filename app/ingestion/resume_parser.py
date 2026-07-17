"""
Resume text extraction from PDF and DOCX files.
Uses pdfplumber for PDFs (handles complex layouts better than PyPDF2)
and python-docx for DOCX files.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def extract_text_from_file(file_path: str) -> str:
    """
    Extract raw text from a resume file (PDF or DOCX).
    
    Args:
        file_path: Path to the resume file.
        
    Returns:
        Extracted text content as a string.
        
    Raises:
        ValueError: If the file type is not supported.
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")
    
    ext = path.suffix.lower()
    
    if ext == ".pdf":
        return _extract_pdf(file_path)
    elif ext == ".docx":
        return _extract_docx(file_path)
    else:
        raise ValueError(
            f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}"
        )


def _extract_pdf(path: str) -> str:
    """Extract text from a PDF file using pdfplumber."""
    import pdfplumber
    
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    
    result = "\n".join(text_parts).strip()
    
    if not result:
        logger.warning(f"No text extracted from PDF: {path} (might be image-based)")
    
    return result


def _extract_docx(path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    from docx import Document
    
    doc = Document(path)
    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
    result = "\n".join(text_parts).strip()
    
    if not result:
        logger.warning(f"No text extracted from DOCX: {path}")
    
    return result


def is_supported_resume(file_path: str) -> bool:
    """Check if a file is a supported resume format."""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS
