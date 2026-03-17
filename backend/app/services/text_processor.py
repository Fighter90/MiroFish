"""
Сервис обработки текста
"""

from typing import List, Optional
from ..utils.file_parser import FileParser, split_text_into_chunks


class TextProcessor:
    """Обработчик текста"""

    @staticmethod
    def extract_from_files(file_paths: List[str]) -> str:
        """Извлечение текста из нескольких файлов"""
        return FileParser.extract_from_multiple(file_paths)

    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """
        Разделение текста

        Args:
            text: Исходный текст
            chunk_size: Размер блока
            overlap: Размер перекрытия

        Returns:
            Список текстовых блоков
        """
        return split_text_into_chunks(text, chunk_size, overlap)

    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        Предобработка текста
        - Удаление лишних пробелов
        - Нормализация переносов строк

        Args:
            text: Исходный текст

        Returns:
            Обработанный текст
        """
        import re

        # Нормализация переносов строк
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Удаление последовательных пустых строк (оставляя максимум два переноса)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Удаление пробелов в начале и конце строк
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text.strip()

    @staticmethod
    def get_text_stats(text: str) -> dict:
        """Получение статистики по тексту"""
        return {
            "total_chars": len(text),
            "total_lines": text.count('\n') + 1,
            "total_words": len(text.split()),
        }
