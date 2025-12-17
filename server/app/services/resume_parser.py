import json
import os
import tempfile
from typing import Optional, Any

import fitz  # PyMuPDF
from docx import Document
from google import genai


RESUME_PARSING_PROMPT = """Parse this resume text and extract structured information.

Return ONLY a JSON object with these fields:

{{
    "name": "Full name of the candidate",
    "email": "email@example.com or null",
    "phone": "phone number or null",
    "skills": ["list", "of", "technical", "and", "soft", "skills"],
    "experience_years": estimated total years of experience (integer),
    "education": [
        {{
            "degree": "degree name",
            "field": "field of study",
            "institution": "school name",
            "year": graduation year or null
        }}
    ],
    "work_history": [
        {{
            "title": "job title",
            "company": "company name",
            "duration": "e.g., 2 years" or null,
            "highlights": ["key achievements or responsibilities"]
        }}
    ],
    "summary": "2-3 sentence professional summary",
    "inferred_culture_preferences": {{
        "preferred_pace": "fast_startup" | "steady" | "slow_methodical" | "unknown",
        "collaboration_preference": "highly_collaborative" | "independent" | "mixed" | "unknown",
        "leadership_style": "hands_on" | "strategic" | "both" | "unknown",
        "work_style_signals": ["any signals about how they prefer to work"]
    }}
}}

RESUME TEXT:
{resume_text}

Return ONLY the JSON object, no other text."""


class ResumeParser:
    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash-lite",
    ):
        self.model = model

        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Either api_key or vertex_project must be provided")

    def extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from a PDF file."""
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)

    def extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from a DOCX file."""
        doc = Document(file_path)
        text_parts = []
        for para in doc.paragraphs:
            text_parts.append(para.text)
        # Also extract from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text_parts.append(cell.text)
        return "\n".join(text_parts)

    def extract_text(self, file_path: str) -> str:
        """Extract text from a resume file (PDF or DOCX)."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self.extract_text_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            return self.extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    async def extract_text_from_bytes(self, file_bytes: bytes, filename: str) -> str:
        """Extract text from file bytes."""
        ext = os.path.splitext(filename)[1].lower()

        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            return self.extract_text(tmp_path)
        finally:
            os.unlink(tmp_path)

    async def parse_resume(self, resume_text: str) -> dict[str, Any]:
        """Parse resume text into structured data using Gemini."""
        prompt = RESUME_PARSING_PROMPT.format(resume_text=resume_text)

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        text = response.text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[ResumeParser] Failed to parse JSON: {e}")
            return {
                "summary": "Unable to parse resume",
                "raw_response": text,
            }

    async def parse_resume_file(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """Extract text and parse a resume file."""
        resume_text = await self.extract_text_from_bytes(file_bytes, filename)
        parsed = await self.parse_resume(resume_text)
        parsed["_resume_text"] = resume_text
        return parsed
