from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models import MethodicEntry, QAEntry
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple
import math
from collections import Counter


# ========== Классы для анализа текста и поиска ==========

class TextAnalyzer:
    """Класс для анализа текста и поиска ключевых слов"""

    @staticmethod
    def clean_text_for_search(text: str) -> str:
        """Очищает текст для поиска"""
        if not text:
            return ""

        text = re.sub(r'\s+', ' ', text.strip())

        text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)

        text = re.sub(r'(\w+)[-\s]+\s*(\w+)', r'\1\2', text)

        return text

    @staticmethod
    def extract_keywords(text: str, min_length: int = 3) -> List[str]:
        """Извлекает ключевые слова из текста"""
        # Убираем стоп-слова
        stop_words = {
            'это', 'что', 'как', 'для', 'или', 'из', 'на', 'по', 'от', 'до',
            'во', 'со', 'при', 'без', 'над', 'под', 'перед', 'после', 'в', 'и',
            'а', 'но', 'же', 'бы', 'ли', 'то', 'ни', 'не', 'у', 'за', 'о', 'об',
            'к', 'ко', 'с', 'со', 'по', 'про', 'через'
        }

        # Находим все слова
        words = re.findall(r'\b\w+\b', text.lower())

        # Фильтруем короткие слова и стоп-слова
        keywords = [w for w in words if len(w) >= min_length and w not in stop_words]

        return list(set(keywords))

    @staticmethod
    def clean_response_text(text: str) -> str:
        """Очищает текст ответа от обрывков и лишних пробелов"""
        if not text:
            return ""

        text = re.sub(r'\s+', ' ', text.strip())

        text = re.sub(r'(\b\w+)[-\s]+\s*(\w+\b)', r'\1\2', text)

        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r'([.,!?;:])(\w)', r'\1 \2', text)

        text = re.sub(r'(\b[а-яa-z]+)[-\s]+(\d+[а-яa-z]*)', r'\1\2', text)

        return text


class SearchEngine:
    """Основной класс для поиска информации"""

    def __init__(self, similarity_threshold: float = 0.65):
        self.similarity_threshold = similarity_threshold

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Вычисляет схожесть двух текстов"""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def search_qa_entries(self, db: Session, question: str, limit: int = 3) -> List[QAEntry]:
        """
        Ищет наиболее похожие вопросы в таблице qa_entries
        """
        question_clean = TextAnalyzer.clean_text_for_search(question).lower()

        all_qa = db.query(QAEntry).all()

        qa_with_similarity = []
        for qa in all_qa:
            qa_question_clean = TextAnalyzer.clean_text_for_search(qa.question).lower()
            similarity = self.calculate_similarity(question_clean, qa_question_clean)

            if similarity >= self.similarity_threshold:
                qa_with_similarity.append({
                    'qa': qa,
                    'similarity': similarity
                })

        qa_with_similarity.sort(key=lambda x: x['similarity'], reverse=True)

        return [item['qa'] for item in qa_with_similarity[:limit]]

    def search_methodic_texts(self, db: Session, query: str, limit: int = 5) -> List[MethodicEntry]:
        """
        Улучшенный поиск в методичках
        """
        query_clean = TextAnalyzer.clean_text_for_search(query)
        keywords = TextAnalyzer.extract_keywords(query_clean, min_length=3)

        query_lower = query.lower()
        if "профессиональные обучающиеся сообщества" in query_lower:
            keywords.extend(["профессиональные", "обучающиеся", "сообщества",
                             "сообщество", "практик", "развитие", "педагог", "учитель"])
        elif "что такое" in query_lower:
            keywords.extend(["это", "является", "означает", "определяется"])

        if not keywords:
            return []

        all_methodics = db.query(MethodicEntry).all()

        scored_results = []
        for methodic in all_methodics:
            score = self._calculate_methodic_relevance(methodic, keywords, query)
            if score >= 2.0:
                scored_results.append({
                    'methodic': methodic,
                    'score': score
                })

        scored_results.sort(key=lambda x: x['score'], reverse=True)

        return [item['methodic'] for item in scored_results[:limit]]

    def _calculate_methodic_relevance(self, methodic: MethodicEntry,
                                      keywords: List[str], query: str) -> float:
        """Вычисляет релевантность методички"""
        score = 0.0

        if methodic.source_title:
            title_lower = methodic.source_title.lower()
            for keyword in keywords:
                if len(keyword) >= 4 and keyword in title_lower:
                    score += 5.0

            if "профессиональные обучающиеся сообщества" in query.lower():
                if "профессиональные обучающиеся сообщества" in title_lower:
                    score += 20.0
                elif "сообщества" in title_lower and (
                        "профессиональные" in title_lower or "обучающиеся" in title_lower):
                    score += 15.0

        if methodic.methodic_text:
            text_clean = TextAnalyzer.clean_text_for_search(methodic.methodic_text).lower()

            first_1000 = text_clean[:1000]
            full_text = text_clean

            for keyword in keywords:
                if len(keyword) < 4:
                    continue

                if keyword in first_1000:
                    score += 3.0

                pattern = r'\b' + re.escape(keyword) + r'\b'
                matches = len(re.findall(pattern, full_text))
                if matches > 0:
                    score += min(matches, 5) * 1.0

            if "что такое" in query.lower():
                sentences = re.split(r'(?<=[.!?])\s+', first_1000)
                for sentence in sentences[:20]:
                    sentence_lower = sentence.lower()
                    has_keywords = any(keyword in sentence_lower for keyword in keywords[:3])
                    is_definition = any(marker in sentence_lower.split()[:3]
                                        for marker in ['это', 'является', 'означает', 'определяется'])

                    if has_keywords and is_definition:
                        score += 10.0
                        break

        return score

    def find_relevant_sentences(self, text: str, keywords: List[str],
                                max_sentences: int = 3) -> List[str]:
        """
        Находит наиболее релевантные предложения в тексте
        """
        if not text or not keywords:
            return []

        clean_text = TextAnalyzer.clean_text_for_search(text)

        sentences = re.split(r'(?<=[.!?…])\s+(?=[А-ЯA-Z0-9«\(])', clean_text)

        scored_sentences = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 500:
                continue

            sentence_lower = sentence.lower()

            score = 0.0

            for keyword in keywords:
                if len(keyword) < 4:
                    continue

                pattern = r'\b' + re.escape(keyword) + r'\b'
                matches = len(re.findall(pattern, sentence_lower))
                score += matches * 2.0

            if score > 0:

                if any(marker in sentence_lower.split()[:3]
                       for marker in ['это', 'является', 'означает', 'определяется']):
                    score += 5.0

                if sentence.endswith(('.', '!', '?', '»')):
                    score += 1.0

                word_count = len(sentence.split())
                if 20 <= word_count <= 50:
                    score += 2.0
                elif 10 <= word_count < 20:
                    score += 1.0

                scored_sentences.append({
                    'sentence': sentence,
                    'score': score,
                    'word_count': word_count
                })

        scored_sentences.sort(key=lambda x: (-x['score'], -x['word_count']))

        result = []
        seen_content = set()

        for item in scored_sentences[:max_sentences * 3]:
            sent = item['sentence']

            if re.search(r'\b[а-яa-z]+[-\s]+\s*\b', sent):
                sent = re.sub(r'(\b[а-яa-z]+)[-\s]+\s*(\b[а-яa-z]+)', r'\1\2', sent)

            if re.search(r'\b[а-яa-z]+-\s*\d+\b', sent):
                continue

            sent_key = sent[:80].lower()
            if sent_key not in seen_content:
                clean_sent = TextAnalyzer.clean_response_text(sent)
                if len(clean_sent) >= 20:
                    result.append(clean_sent)
                    seen_content.add(sent_key)
                    if len(result) >= max_sentences:
                        break

        return result

    def search_methodics_with_context(self, db: Session, question: str,
                                      limit: int = 5) -> Dict:
        """
        Основная функция поиска с контекстом
        """
        qa_results = self.search_qa_entries(db, question, limit=limit)

        keywords = TextAnalyzer.extract_keywords(question, min_length=3)

        methodic_results = self.search_methodic_texts(db, question, limit)

        methodic_contexts = []

        for methodic in methodic_results:
            if methodic.methodic_text:
                relevant_sentences = self.find_relevant_sentences(
                    methodic.methodic_text,
                    keywords,
                    max_sentences=3
                )

                if relevant_sentences:
                    relevance_score = len(relevant_sentences)

                    for sentence in relevant_sentences:
                        if any(keyword in sentence.lower() for keyword in keywords[:5]):
                            relevance_score += 1

                    methodic_contexts.append({
                        'methodic': methodic,
                        'relevant_sentences': relevant_sentences,
                        'relevance_score': relevance_score,
                        'source_title': methodic.source_title or "Методический материал"
                    })

        methodic_contexts.sort(key=lambda x: x['relevance_score'], reverse=True)

        return {
            'qa_results': qa_results,
            'methodic_contexts': methodic_contexts[:limit],
            'keywords': keywords,
            'question': question
        }


class ResponseFormatter:
    """Класс для форматирования ответов"""

    @staticmethod
    def format_definition_answer(search_results: dict, question: str) -> str:
        """
        Форматирует ответ на вопрос о определении
        """
        parts = ["**Ответ на основе методических материалов:**"]

        term_match = re.search(r'что такое\s+(.+?)(?:\?|$)', question.lower())
        if term_match:
            term = term_match.group(1).strip()
            parts.append(f"\n**Определение {term}:**")

        definition_found = False

        for ctx in search_results.get('methodic_contexts', []):
            methodic = ctx['methodic']
            source_title = ctx['source_title']

            for sentence in ctx.get('relevant_sentences', []):
                sentence_lower = sentence.lower()
                is_definition = any(marker in sentence_lower.split()[:3]
                                    for marker in ['это', 'является', 'означает', 'определяется',
                                                   'подразумевает', 'представляет собой'])

                if is_definition or "профессиональные обучающиеся сообщества" in sentence_lower:
                    clean_sentence = TextAnalyzer.clean_response_text(sentence)
                    if len(clean_sentence) > 30:
                        parts.append(f"\n• {clean_sentence}")
                        parts.append(f"  *Источник: {source_title}*")
                        definition_found = True
                        break

            if definition_found and len(parts) > 4:
                break

        if not definition_found:
            parts.append("\nВ методических материалах не найдено четкого определения, но есть следующая информация:")

            relevant_info = []
            sources_used = set()

            for ctx in search_results.get('methodic_contexts', []):
                methodic = ctx['methodic']
                source_title = ctx['source_title']

                if source_title in sources_used:
                    continue

                for sentence in ctx.get('relevant_sentences', []):
                    clean_sentence = TextAnalyzer.clean_response_text(sentence)
                    if len(clean_sentence) > 40:
                        relevant_info.append(f"• {clean_sentence}")
                        sources_used.add(source_title)
                        break

                if len(relevant_info) >= 2:
                    break

            if relevant_info:
                parts.extend(relevant_info)
                parts.append(f"\n**Источники:** {', '.join(list(sources_used)[:3])}")
            else:
                parts.append("\nК сожалению, в методических материалах не найдено информации по данному вопросу.")
                parts.append("Рекомендуется обратиться к дополнительным источникам.")

        return "\n".join(parts)

    @staticmethod
    def create_clean_response(search_results: dict, question: str) -> str:
        """
        Создает чистый, структурированный ответ
        """
        parts = ["**Ответ на основе методических материалов:**"]

        question_lower = question.lower()

        if "что такое" in question_lower:
            return ResponseFormatter.format_definition_answer(search_results, question)

        keywords = search_results.get('keywords', [])

        relevant_points = []
        sources_used = set()

        for ctx in search_results.get('methodic_contexts', []):
            methodic = ctx['methodic']
            source_title = ctx['source_title']

            if source_title in sources_used:
                continue

            relevant_sentences = ctx.get('relevant_sentences', [])
            if relevant_sentences:
                best_sentence = None
                best_score = 0

                for sentence in relevant_sentences:
                    sentence_lower = sentence.lower()
                    score = sum(1 for keyword in keywords if keyword in sentence_lower)

                    if score > best_score:
                        best_score = score
                        best_sentence = sentence

                if best_sentence and len(best_sentence) > 30:
                    clean_sentence = TextAnalyzer.clean_response_text(best_sentence)
                    relevant_points.append(f"• {clean_sentence}")
                    sources_used.add(source_title)

            if len(relevant_points) >= 3:
                break

        if relevant_points:
            parts.append("")
            parts.extend(relevant_points)

            if sources_used:
                parts.append(f"\n**Источники:**")
                for source in list(sources_used)[:3]:
                    parts.append(f"• {source}")
        else:
            parts.append("\nПо данному вопросу в методических материалах найдена ограниченная информация.")
            parts.append("Рекомендуется уточнить вопрос или обратиться к дополнительным источникам.")

        return "\n".join(parts)


# ========== Основные функции для использования ==========

def search_methodics_with_context(db: Session, question: str, limit: int = 5) -> Dict:
    """Основная функция поиска (обертка для совместимости)"""
    engine = SearchEngine()
    return engine.search_methodics_with_context(db, question, limit)


def format_context_for_prompt(search_results: dict, question: str) -> str:
    """Форматирует контекст для промпта (для обратной совместимости)"""
    formatter = ResponseFormatter()
    return formatter.create_clean_response(search_results, question)


def get_enhanced_answer(db: Session, question: str) -> str:
    """Получает улучшенный ответ на вопрос"""
    engine = SearchEngine()
    formatter = ResponseFormatter()
    search_results = engine.search_methodics_with_context(db, question)

    return formatter.create_clean_response(search_results, question)


# ========== Функции для обратной совместимости ==========

def calculate_similarity(text1: str, text2: str) -> float:
    """Вычисляет схожесть двух текстов от 0 до 1"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def search_qa_entries(db: Session, question: str, threshold: float = 0.6, limit: int = 3):
    """Совместимость со старым кодом"""
    engine = SearchEngine(similarity_threshold=threshold)
    return engine.search_qa_entries(db, question, limit)


def clean_text_for_search(text: str) -> str:
    """Совместимость со старым кодом"""
    return TextAnalyzer.clean_text_for_search(text)


def search_methodic_texts(db: Session, query: str, limit: int = 5):
    """Совместимость со старым кодом"""
    engine = SearchEngine()
    return engine.search_methodic_texts(db, query, limit)


def find_relevant_sentences(text: str, question: str, max_sentences: int = 3) -> list:
    """Совместимость со старым кодом"""
    engine = SearchEngine()
    keywords = TextAnalyzer.extract_keywords(question)
    return engine.find_relevant_sentences(text, keywords, max_sentences)
