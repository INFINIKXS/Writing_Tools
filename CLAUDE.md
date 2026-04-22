# Writing Tools App - Project Context & Rules

This document provides system instructions for AI coding assistants (Claude, Gemini, etc.) working on this repository.

## Project Overview
A web-based Writing Tools application designed to process, extract, and verify documents (including PDFs), handle citations constraints (APA, Harvard, Vancouver), and perform offline text analysis and AI humanization.

## Tech Stack
*   **Backend:** Python, FastAPI. Core libraries include `pypdf`, `google-genai`, `spacy`, `fuzzywuzzy`, and PDF/OCR tools (`pdf2image`, `pytesseract`).
*   **Frontend:** React 19 (Functional/Hooks), Vite, Tailwind CSS, `pdf-lib`, and `react-pdf`.

## Workflow & Commands
*   **Backend:** Activate the local `venv`, install dependencies via `pip install -r requirements.txt`, run the dev server via FastAPI/Uvicorn (e.g. `uvicorn main:app --reload`).
*   **Frontend:** Located in `frontend/`. Run `npm run dev` to start the Vite server. Use `npm run lint` for code quality checks.

## Architecture & Coding Conventions

### Backend (Python)
1.  **Environment:** ALWAYS assume we are operating within the local virtual environment (`venv`). Do not suggest or attempt global pip installs.
2.  **Data Processing:** When writing data-fetching scripts or extraction tools, implement robust error handling, respect rate limits, and default to modular architectures.
3.  **Verbatim Priority:** When building tools to parse files (e.g., extracting sentences from PDFs), strictly prioritize verbatim accuracy. **Do not hallucinate, summarize, or alter source text under any circumstances.**
4.  **Citations:** When handling formatting guides (APA, Harvard, Vancouver), strictly adhere to the programmatic rules defined in the current modules.
5.  **String Safety:** Treat string encoding issues (e.g. UTF-8 character read errors) as critical bugs. Resolve them using safe string decoding methods immediately.
6.  **Observability:** Prioritize clear, structured logging over standard `print()` statements for easier debugging.

### Frontend (React)
1.  **Hooks First:** Default to functional components and React Hooks. Avoid class components entirely.
2.  **Clean UI:** Keep UI component logic clean. Offload heavy data transformations or verification checks to separate utility files before passing data to the views.
3.  **Styling:** Use Tailwind CSS for designing and creating responsive layouts. Avoid inline styles where possible.

## Boundaries
*   Do not overwrite existing citation formatters with generic logic.
*   Never modify the existing `.antigravityrules` without explicit confirmation.
