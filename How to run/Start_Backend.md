# How to Start the Backend Server

The backend of the Writing Tools Web App is built with Python and FastAPI. It needs to run simultaneously with the frontend server.

1. **Open a new terminal window** (Command Prompt or PowerShell).

2. **Navigate to the backend directory:**

   ```powershell
   cd c:\Users\Paradox-Labs\Documents\Projects\Writing_Tools\backend
   ```

3. **Activate the virtual environment:**

   ```powershell
   .\venv\Scripts\activate
   ```

   *(You should see `(venv)` appear at the beginning of your command prompt line).*

4. **Start the FastAPI development server:**

   ```powershell
   uvicorn main:app --reload
   ```

The backend server will now be running at `http://localhost:8000` and will automatically restart if you make changes to the Python files.

**Important Note:** Make sure you have created a `.env` file in the `backend` folder (you can rename `.env.example`) and inserted your `GOOGLE_API_KEY` into it!
