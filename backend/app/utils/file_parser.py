"""
Инструмент разбора файлов
Поддержка извлечения текста из PDF, Markdown, TXT
"""

import os
from pathlib import Path
from typing import List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    Чтение текстового файла с автоопределением кодировки при ошибке UTF-8.

    Многоуровневая стратегия:
    1. Сначала попытка декодирования UTF-8
    2. Определение кодировки через charset_normalizer
    3. Откат на chardet
    4. Финальный вариант: UTF-8 + errors='replace'

    Args:
        file_path: Путь к файлу

    Returns:
        Декодированное текстовое содержимое
    """
    data = Path(file_path).read_bytes()

    # Сначала пробуем UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # Попытка определения кодировки через charset_normalizer
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass

    # Откат на chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass

    # Финальный вариант: UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'

    return data.decode(encoding, errors='replace')


class FileParser:
    """Парсер файлов"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        Извлечение текста из файла

        Args:
            file_path: Путь к файлу

        Returns:
            Извлечённое текстовое содержимое
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Неподдерживаемый формат файла: {suffix}")

        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)

        raise ValueError(f"Невозможно обработать формат файла: {suffix}")

    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Извлечение текста из PDF"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("Необходимо установить PyMuPDF: pip install PyMuPDF")

        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """Извлечение текста из Markdown с автоопределением кодировки"""
        return _read_text_with_fallback(file_path)

    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """Извлечение текста из TXT с автоопределением кодировки"""
        return _read_text_with_fallback(file_path)

    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        Извлечение текста из нескольких файлов и объединение

        Args:
            file_paths: Список путей к файлам

        Returns:
            Объединённый текст
        """
        all_texts = []

        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== Документ {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== Документ {i}: {file_path} (ошибка извлечения: {str(e)}) ===")

        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[str]:
    """
    Разделение текста на фрагменты

    Args:
        text: Исходный текст
        chunk_size: Количество символов в каждом фрагменте
        overlap: Количество символов перекрытия

    Returns:
        Список текстовых фрагментов
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Попытка разделить по границе предложения
        if end < len(text):
            # Поиск ближайшего конца предложения
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Следующий фрагмент начинается с позиции перекрытия
        start = end - overlap if end < len(text) else len(text)

    return chunks
