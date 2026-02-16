from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class KnowledgeType(str, Enum):
    foundational = "foundational"
    practical = "practical"
    strategic = "strategic"


class KnowledgePoint(BaseModel):
    name: str
    type: KnowledgeType


class KnowledgePoints(BaseModel):
    knowledge_points: List[KnowledgePoint]

class KnowledgeDraft(BaseModel):
    title: str
    content: str
    sources_used: Optional[List[dict]] = None


class DocumentStructure(BaseModel):
    title: str
    overview: str
    summary: str


class SingleChoiceQuestion(BaseModel):
    question: str
    options: List[str]
    correct_option: int | str
    explanation: str | None = None


class MultipleChoiceQuestion(BaseModel):
    question: str
    options: List[str]
    correct_options: List[int | str]
    explanation: str | None = None


class TrueFalseQuestion(BaseModel):
    question: str
    correct_answer: bool
    explanation: str | None = None


class ShortAnswerQuestion(BaseModel):
    question: str
    expected_answer: str
    explanation: str | None = None


class DocumentQuiz(BaseModel):
    single_choice_questions: List[SingleChoiceQuestion] = Field(default_factory=list)
    multiple_choice_questions: List[MultipleChoiceQuestion] = Field(default_factory=list)
    true_false_questions: List[TrueFalseQuestion] = Field(default_factory=list)
    short_answer_questions: List[ShortAnswerQuestion] = Field(default_factory=list)


def parse_knowledge_points(data) -> KnowledgePoints:
    return KnowledgePoints.model_validate(data)


def parse_knowledge_draft(data) -> KnowledgeDraft:
    return KnowledgeDraft.model_validate(data)


def parse_document_structure(data) -> DocumentStructure:
    return DocumentStructure.model_validate(data)


def parse_document_quiz(data) -> DocumentQuiz:
    return DocumentQuiz.model_validate(data)


class ContentSection(BaseModel):
    title: str
    summary: str


class ContentOutline(BaseModel):
    title: str
    sections: List[ContentSection] = Field(default_factory=list)


class QuizPair(BaseModel):
    question: str
    answer: str


class LearningContent(BaseModel):
    title: str
    overview: str
    content: str
    summary: str
    quizzes: List[QuizPair] = Field(default_factory=list)
