# WiseBuy AI

WiseBuy AI is a Flask-based product purchase assistant that helps shoppers compare products from Amazon and Walmart. It includes a conversational advisor, image-based product search, account and chat history support, and optional sentiment scoring for product ranking.

## Features

- Conversational product recommendations powered by Groq
- Amazon product search through RapidAPI
- Walmart product search through OpenWebNinja
- Image-to-product search using a Groq vision model
- User signup, login, password reset, chat history, and saved result sets
- Optional DistilBERT sentiment scoring for ranking product review blurbs
- Flask web UI with a chatbot-style shopping experience

## Project Structure

```text
projectDemo/
  app/
    app.py                  # Flask app and API routes
    templates/index.html    # Web interface
  chatbot/
    chatbot.py              # CLI chatbot prototype
  docs/
    system-architecture.svg
    user-workflow.svg
  scraper/
    amazon_api.py
    walmart_api.py
    sentiment_analyzer.py
    sentiment_model/        # Sentiment model config/tokenizer files
  requirements.txt
```

## Setup

1. Create and activate a virtual environment.

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root.

```env
FLASK_SECRET_KEY=replace-with-a-random-secret
GROQ_API_KEY=your-groq-api-key
RAPIDAPI_KEY=your-rapidapi-key
OPENWEBNINJA_KEY=your-openwebninja-key
GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
WISEBUY_DB_PATH=app/wisebuy.db
```

Optional password reset email settings:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password
SMTP_FROM=no-reply@example.com
SMTP_TLS=1
```

## Running the Web App

```bash
python app/app.py
```

Then open `http://127.0.0.1:5000`.

## Running the CLI Chatbot

```bash
python chatbot/chatbot.py
```

## Sentiment Model Note

The local DistilBERT weight file `scraper/sentiment_model/model.safetensors` is intentionally excluded from Git because it is larger than GitHub's standard file size limit. To enable sentiment scoring, place the model weights at:

```text
scraper/sentiment_model/model.safetensors
```

If the file is missing, the application falls back to neutral sentiment scores and continues running.

## Notes

- `.env` and the local SQLite database are ignored so secrets and local user data are not uploaded.
- API keys are optional for local UI testing, but real product search and AI responses require the corresponding keys.
