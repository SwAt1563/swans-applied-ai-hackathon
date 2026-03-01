# 🦢 Swans Applied AI Hackathon: Legal Intake Automation

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00a393.svg)](https://fastapi.tiangolo.com)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange)](https://ai.google.dev/)
[![Clio API](https://img.shields.io/badge/Integration-Clio%20Manage-blue)](https://docs.developers.clio.com/)

A production-ready AI Legal Engineering solution built for the Swans Applied AI Hackathon. This application automates the ingestion of police reports, eliminates manual data entry in Clio Manage, and accelerates speed-to-lead by instantly generating and emailing Retainer Agreements to potential personal injury clients.



## The Business Problem & Solution

**The Problem:** Personal injury firms lose high-value cases due to slow manual data entry. When a potential client submits a messy, scanned police report, paralegals spend critical hours deciphering the PDF and typing details into Clio Manage. By the time the retainer is generated, the client has often signed with a faster competitor.

**The Solution:** This app completely automates the intake bottleneck. It acts as an autonomous agent that:
1. **Reads & Extracts:** Uses Google Gemini AI to deterministically extract accident details, parties, and vehicles from unstructured PDF police reports.
2. **Syncs to Clio:** Automatically maps and pushes these details to specific Matter Custom Fields in Clio Manage via a custom OAuth2 SDK.
3. **Generates Retainers:** Triggers Clio's Document Automation to generate a pre-filled Retainer Agreement PDF.
4. **Calendars Deadlines:** Calculates the 8-year Statute of Limitations and automatically adds it to the Responsible Attorney's Clio calendar.
5. **Closes the Lead:** Sends a personalized, context-aware HTML email to the client with the agreement attached and dynamically routes them to an in-office or virtual scheduling link based on the season.

---

##  Architecture & Tech Stack

This project was built from scratch as a fully custom, server-side web application to ensure production-grade reliability, bypassing the limitations of no-code platforms.

* **Backend Framework:** Python / FastAPI (High-performance, async routing).
* **AI Engine:** `google-genai` (Configured with strict Pydantic models to enforce structured, hallucination-free JSON outputs from messy PDFs).
* **Integration:** Custom asynchronous Clio V4 API Wrapper utilizing `httpx` and file-based token management for secure, per-user OAuth flows.
* **Document Processing:** `python-multipart` for API ingestion, `python-docx` for template handling.
* **Communications:** Built-in Python `smtplib` and `email.mime` for automated HTML email dispatch.
* **Hosting:** Deployed to Cloud via Render / Leapcell.

---

##  Workflow Overview

1. **Authentication:** User logs in via Clio Manage OAuth2 (US Region). The app securely stores access/refresh tokens.
2. **Environment Initialization:** The system checks the user's Clio account for the required Custom Fields (e.g., Accident Date, Defendant Name). If missing, it auto-creates them via API.
3. **Ingestion:** User uploads a raw PDF police report to the FastAPI endpoint.
4. **Extraction:** Gemini AI processes the document and returns a strictly typed JSON object containing the accident data.
5. **Clio Sync:** The custom SDK patches the existing Clio Matter, updates the Contact, and sets the 8-year Statute of Limitations calendar event.
6. **Dispatch:** The system sends a formatted HTML email to the client with the dynamic Calendly link and the PDF Retainer Agreement attached.

---

##  Local Setup & Installation

### Prerequisites
* Python 3.11 or higher
* A US-region Clio Manage Developer Account
* Google Gemini API Key
* App Password for SMTP Email Sending (e.g., Gmail App Password) `[Optional]`

### 1. Clone the repository
```bash
git clone [https://github.com/SwAt1563/swans-applied-ai-hackathon.git](https://github.com/SwAt1563/swans-applied-ai-hackathon.git)
cd swans-applied-ai-hackathon

```

### 2. Install Dependencies

It is recommended to use a virtual environment.

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt

```

### 3. Environment Variables

Create a `.env` file in the root directory and add the following keys:

```env
# Clio OAuth Credentials (US Region)
CLIO_CLIENT_ID=your_clio_client_id
CLIO_CLIENT_SECRET=your_clio_client_secret
CLIO_REDIRECT_URI=[http://127.0.0.1:8000/oauth/callback](http://127.0.0.1:8000/oauth/callback)

# Google Gemini
GOOGLE_API_KEY=your_gemini_api_key


```

### 4. Run the Server

```bash
uvicorn main:app --reload

```

Navigate to `http://127.0.0.1:8000` in your browser to access the interface.



##  Video Walkthrough & Demo

* **Live App Deployment:** https://swans-applied-ai-hackathon.onrender.com
* **Architectural Walkthrough (Loom/Drive):** https://drive.google.com/file/d/1wciqsS63a7RwLCNj0aoKSeudVtZvp3Bj/view?usp=sharing

*Note: To test the live application, you must authenticate using a North American (US) Clio Manage account.*

---

*Built for the 2026 Swans Applied AI Hackathon.*
