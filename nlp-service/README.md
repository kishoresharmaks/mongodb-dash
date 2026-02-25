# NLP Service for MongoDB

Natural Language Interface for MongoDB using LLMs (OpenAI, Gemini, or Local LLM).

## Features

- 🤖 Multi-LLM Support (OpenAI GPT, Google Gemini, Local LLM via LM Studio)
- 🔍 Natural language to MongoDB query translation
- 🛡️ Query safety validation
- ⚡ FastAPI with async support
- 📊 Automatic schema inference

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` and set:

- `MONGODB_ATLAS_URI`: Your MongoDB Atlas connection string
- `DATABASE_NAME`: Database to query (e.g., `sample_mflix`)
- `LLM_PROVIDER`: Choose `openai`, `gemini`, or `local`
- API keys for your chosen provider

### 3. LLM Provider Setup

#### Option A: Google Gemini (Recommended for Free Tier)

```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-google-api-key
GEMINI_MODEL=gemini-3-flash-preview
```

Get API key: https://aistudio.google.com/app/apikey

#### Option B: OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-3.5-turbo
```

#### Option C: Local LLM (LM Studio)

1. Download LM Studio: https://lmstudio.ai/
2. Download a model (e.g., Llama 3 8B)
3. Start local server in LM Studio (port 1234)
4. Configure:

```env
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
LOCAL_LLM_MODEL=llama-3-8b-instruct
```

### 4. Run Service

```bash
python main.py
```

Or with uvicorn:

```bash
uvicorn main:app --reload --port 8000
```

## API Endpoints

### POST /translate

Translate natural language to MongoDB query.

**Request:**
```json
{
  "query": "Show movies from 1999 with rating above 8",
  "database": "sample_mflix",
  "collection": "movies"
}
```

**Response:**
```json
{
  "success": true,
  "mql_query": {...},
  "results": [...],
  "explanation": "Found 15 results...",
  "metadata": {
    "provider": "gemini",
    "model": "gemini-pro"
  }
}
```

### GET /health

Health check endpoint.

## Testing

```bash
pytest tests/ -v
```

## Example Queries

- "Show movies from 1999"
- "Find movies with rating above 8"
- "Top 10 highest rated movies"
- "Count movies by year"
- "Movies directed by Christopher Nolan"
