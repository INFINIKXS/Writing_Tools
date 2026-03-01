# How to Run the Writing Tools Web App

This application consists of a Python FastAPI backend and a React Vite frontend. You will need two separate terminal windows to run them simultaneously.

## Prerequisites

- **Python 3.8+** installed.
- **Node.js** installed (v16+).
- A **Google Gemini API Key**.

---

## 1. Setting up the API Key (First time only)

Before running the application, you must provide your Gemini API key to the backend.

1. Navigate to the `backend` folder.
2. Rename the file `.env.example` to `.env`.
3. Open `.env` and replace `your_api_key_here` with your actual Google API Key.

   ```env
   GOOGLE_API_KEY=AIzaSyA...
   ```

---

## 2. Running the Backend Server

Open a new terminal (PowerShell or Command Prompt).

1. **Navigate to the backend directory:**

   ```powershell
   cd c:\Users\Paradox-Labs\Documents\Projects\Writing_Tools\backend
   ```

2. **Activate the virtual environment:**

   ```powershell
   .\venv\Scripts\activate
   ```

   *(You should see `(venv)` appear in your prompt).*

3. **Start the FastAPI server:**

   ```powershell
   uvicorn main:app --reload
   ```

   The backend will now be running at `http://localhost:8000`. Leave this terminal window open.

---

## 3. Running the Frontend Server

Open a **second** new terminal window.

1. **Navigate to the frontend directory:**

   ```powershell
   cd c:\Users\Paradox-Labs\Documents\Projects\Writing_Tools\frontend
   ```

2. **Start the Vite development server:**

   ```powershell
   npm run dev
   ```

3. **Open the application:**
   The terminal will output a local URL (usually `http://localhost:5173`). Open this URL in your web browser.

You can now use the Writing Tools interface, and it will communicate with your local backend server!
