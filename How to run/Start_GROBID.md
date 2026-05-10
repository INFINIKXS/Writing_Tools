# How to Run GROBID (Metadata Extraction Service)

GROBID is a machine-learning based PDF extraction tool that powers **Layer 3** of the academic reference extraction pipeline. It runs as a standalone background service via Docker.

> [!NOTE]
> **Do I have to run this?**
> No, the app will not crash if GROBID is offline. It will gracefully degrade to using `pdf2doi` and CrossRef APIs. However, keeping GROBID running significantly improves accuracy on messy or older PDFs.

## Prerequisites
You must have [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running on your Windows machine.

## How to Start GROBID (Testing / Development)

Because Docker commands communicate directly with the Docker Desktop engine, **it does not matter which folder you are in** when you run this command. You can run it from the project root or your home directory.

1. Open a new Command Prompt or PowerShell window.
2. Run the following command:
   ```bash
   docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
   ```
3. Wait until you see a log message similar to `Server started on port 8070`.
4. Your FastAPI backend will now automatically detect GROBID and use it for PDF uploads.
5. To stop the server, simply press `Ctrl+C` in the terminal.

## How to Start GROBID (Background Daemon)

If you don't want to keep a terminal window open just for GROBID, you can run it as a background "daemon".

1. Run this command instead:
   ```bash
   docker run -d --name grobid --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
   ```
2. The command will instantly return a long ID string. GROBID is now running invisibly in the background.
3. You can verify it is running by opening the **Docker Desktop** app and looking at your "Containers" tab.
4. To stop it, either click the "Stop" square in Docker Desktop, or run:
   ```bash
   docker stop grobid
   ```

## Production Requirements
> [!WARNING]
> GROBID uses machine learning models written in Java. In a production environment, the server hosting the GROBID container should have a minimum of **2GB to 4GB of RAM** to prevent out-of-memory crashes during heavy usage.
