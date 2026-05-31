from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
import sys
import os
import re
import base64
import json
import sqlite3
import secrets
import hashlib
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from groq import Groq
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scraper")))
from amazon_api import search_products
from walmart_api import search_walmart_products
from sentiment_analyzer import score_batch

app = Flask(__name__)
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    print("FLASK_SECRET_KEY is not set; using a temporary session key for this run.")
app.secret_key = FLASK_SECRET_KEY or secrets.token_urlsafe(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
DB_PATH = os.getenv("WISEBUY_DB_PATH", os.path.join(os.path.dirname(__file__), "wisebuy.db"))
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_SEARCH_QUERIES = 5
RECOMMENDATION_COUNT = 12
PASSWORD_MIN_LENGTH = 8
PASSWORD_HASH_ITERATIONS = 260000
RESET_TOKEN_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "20"))
ALLOW_DEV_RESET_CODE = os.getenv("ALLOW_DEV_RESET_CODE", "0") == "1"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
LOCAL_RESET_HOSTS = {"127.0.0.1", "localhost", "::1"}
SEARCH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "buy", "by", "for",
    "from", "in", "is", "it", "of", "on", "or", "product", "search", "the",
    "this", "to", "with",
}


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                password_hash TEXT,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS result_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                query TEXT NOT NULL,
                response TEXT NOT NULL,
                products_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chats_user_updated ON chats(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages(chat_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_results_chat_created ON result_sets(chat_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id, created_at DESC);
            """
        )
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(users)")
        }
        if "is_anonymous" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN is_anonymous INTEGER NOT NULL DEFAULT 0")
        if "email" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "password_hash" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "last_login_at" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")


def row_to_dict(row):
    return dict(row) if row else None


def normalize_email(email):
    return re.sub(r"\s+", "", str(email or "").strip().lower())[:254]


def is_valid_email(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def validate_password(password):
    password = str(password or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must include at least one letter and one number."
    return None


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password, stored_hash):
    try:
        algorithm, iterations, salt, expected = str(stored_hash or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password).encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return secrets.compare_digest(digest, expected)
    except Exception:
        return False


def token_hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def parse_iso(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return None


def create_user(name, is_anonymous=False):
    clean_name = (name or "").strip()[:40] or "Guest"
    stamp = now_iso()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO users (name, is_anonymous, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (clean_name, 1 if is_anonymous else 0, stamp, stamp),
        )
        return cur.lastrowid


def get_user(user_id):
    if not user_id:
        return None
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def get_user_by_email(email):
    clean_email = normalize_email(email)
    if not clean_email:
        return None
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM users WHERE email = ?", (clean_email,)).fetchone())


def public_user(user):
    if not user:
        return None
    return {
        "id": user["id"],
        "name": user.get("name") or "Account",
        "email": user.get("email") or "",
    }


def create_account(name, email, password):
    clean_name = re.sub(r"\s+", " ", str(name or "").strip())[:40] or "WiseBuy User"
    clean_email = normalize_email(email)
    password_error = validate_password(password)

    if not is_valid_email(clean_email):
        return None, "Enter a valid email address."
    if password_error:
        return None, password_error
    if get_user_by_email(clean_email):
        return None, "An account already exists for that email."

    stamp = now_iso()
    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO users (name, email, password_hash, is_anonymous, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (clean_name, clean_email, hash_password(password), stamp, stamp),
        )
        return cur.lastrowid, None


def authenticate_user(email, password):
    user = get_user_by_email(email)
    if not user or user.get("is_anonymous") or not verify_password(password, user.get("password_hash")):
        return None
    return user


def set_login_session(user_id):
    session["active_user_id"] = user_id
    session.pop("active_chat_id", None)
    session.pop("anonymous_chat_id", None)
    with get_db() as db:
        db.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now_iso(), now_iso(), user_id),
        )


def clear_login_session():
    session.pop("active_user_id", None)
    session.pop("active_chat_id", None)
    session.pop("anonymous_chat_id", None)


def current_profile_user_id(candidate=None):
    user_id = session.get("active_user_id")
    user = get_user(user_id)
    if not user or user.get("is_anonymous") or not user.get("email") or not user.get("password_hash"):
        return None
    return user["id"]


def ensure_anonymous_user():
    user_id = session.get("anonymous_user_id")
    user = get_user(user_id)
    if user and user.get("is_anonymous"):
        return user["id"]

    user_id = create_user("Guest", is_anonymous=True)
    session["anonymous_user_id"] = user_id
    return user_id


def resolve_user_id(candidate=None):
    user_id = current_profile_user_id(candidate)
    if not user_id:
        raise ValueError("Login required")
    session["active_user_id"] = user_id
    return user_id


def create_chat(user_id, title="New chat"):
    stamp = now_iso()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO chats (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, title, stamp, stamp),
        )
        return cur.lastrowid


def get_chat(chat_id, user_id=None):
    if not chat_id:
        return None
    params = [chat_id]
    sql = "SELECT * FROM chats WHERE id = ?"
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    with get_db() as db:
        return row_to_dict(db.execute(sql, params).fetchone())


def resolve_chat_id(user_id, candidate=None, session_key="active_chat_id", create_if_missing=True):
    chat_id = candidate or session.get(session_key)
    chat = get_chat(chat_id, user_id)
    if not chat:
        chat_id = create_chat(user_id) if create_if_missing else None

    if chat_id:
        session[session_key] = chat_id
    else:
        session.pop(session_key, None)
    return chat_id


def list_chats(user_id):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                c.*,
                COUNT(DISTINCT r.id) AS result_count,
                (
                    SELECT m.content
                    FROM messages m
                    WHERE m.chat_id = c.id
                    ORDER BY m.created_at DESC, m.id DESC
                    LIMIT 1
                ) AS last_message
            FROM chats c
            LEFT JOIN result_sets r ON r.chat_id = c.id
            WHERE c.user_id = ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id DESC
            """,
            (user_id,),
        )
        return [row_to_dict(row) for row in rows]


def get_chat_messages(chat_id, limit=None):
    sql = "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC, id ASC"
    params = [chat_id]
    if limit:
        sql = (
            "SELECT * FROM ("
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at DESC, id DESC LIMIT ?"
            ") ORDER BY created_at ASC, id ASC"
        )
        params.append(limit)
    with get_db() as db:
        return [row_to_dict(row) for row in db.execute(sql, params)]


def touch_chat(chat_id):
    with get_db() as db:
        db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now_iso(), chat_id))


def add_message(chat_id, role, content):
    stamp = now_iso()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, stamp),
        )
        db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (stamp, chat_id))
        return cur.lastrowid


def maybe_update_chat_title(chat_id, text):
    chat = get_chat(chat_id)
    if not chat or chat["title"] != "New chat":
        return
    title = re.sub(r"\s+", " ", text.strip())[:48] or "New chat"
    with get_db() as db:
        db.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?", (title, now_iso(), chat_id))


def add_result_set(chat_id, source, query, response, products):
    stamp = now_iso()
    clean_products = json.dumps(products or [], ensure_ascii=False)
    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO result_sets (chat_id, source, query, response, products_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, source, query or "Product search", response or "", clean_products, stamp),
        )
        db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (stamp, chat_id))
        return cur.lastrowid


def list_result_sets(chat_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM result_sets WHERE chat_id = ? ORDER BY created_at DESC, id DESC",
            (chat_id,),
        )
        result_sets = []
        for row in rows:
            item = row_to_dict(row)
            try:
                item["products"] = json.loads(item.pop("products_json") or "[]")
            except Exception:
                item["products"] = []
            result_sets.append(item)
        return result_sets


def empty_chat_detail():
    return {
        "chat": None,
        "messages": [],
        "result_sets": [],
        "latest_result_id": None,
    }


def chat_detail(chat_id):
    if not chat_id:
        return empty_chat_detail()

    messages = get_chat_messages(chat_id)
    result_sets = list_result_sets(chat_id)
    return {
        "chat": get_chat(chat_id),
        "messages": messages,
        "result_sets": result_sets,
        "latest_result_id": result_sets[0]["id"] if result_sets else None,
    }


def public_message_history(chat_id, limit=12):
    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in get_chat_messages(chat_id, limit=limit)
    ]


def auth_payload(user_id=None):
    user = get_user(user_id or current_profile_user_id())
    authenticated = bool(user and not user.get("is_anonymous") and user.get("email"))
    return {
        "user": public_user(user) if authenticated else None,
        "active_user_id": user["id"] if authenticated else None,
        "active_chat_id": None,
        "authenticated": authenticated,
        "chats": list_chats(user["id"]) if authenticated else [],
        "detail": empty_chat_detail(),
    }


def is_local_request():
    host = (request.host or "").split(":", 1)[0].strip().lower()
    return host in LOCAL_RESET_HOSTS


def create_password_reset(user_id):
    token = secrets.token_urlsafe(24)
    stamp = now_iso()
    expires = (datetime.utcnow() + timedelta(minutes=RESET_TOKEN_MINUTES)).replace(microsecond=0).isoformat() + "Z"
    with get_db() as db:
        db.execute(
            "UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
            (stamp, user_id),
        )
        db.execute(
            """
            INSERT INTO password_resets (user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, token_hash(token), expires, stamp),
        )
    return token, expires


def send_password_reset_email(user, token):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_from = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not smtp_host or not smtp_from:
        return False

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_TLS", "1") == "1"

    msg = EmailMessage()
    msg["Subject"] = "WiseBuy AI password reset"
    msg["From"] = smtp_from
    msg["To"] = user["email"]
    msg.set_content(
        "Use this password reset code in WiseBuy AI:\n\n"
        f"{token}\n\n"
        f"This code expires in {RESET_TOKEN_MINUTES} minutes. If you did not request it, ignore this email."
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Password reset email failed: {e}")
        return False


def reset_password_with_token(email, token, new_password):
    user = get_user_by_email(email)
    password_error = validate_password(new_password)
    if password_error:
        return False, password_error
    if not user:
        return False, "Invalid or expired reset code."

    now = datetime.utcnow()
    with get_db() as db:
        row = db.execute(
            """
            SELECT * FROM password_resets
            WHERE user_id = ? AND token_hash = ? AND used_at IS NULL
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user["id"], token_hash(token)),
        ).fetchone()
        reset = row_to_dict(row)
        expires_at = parse_iso(reset["expires_at"]) if reset else None
        if not reset or not expires_at or expires_at < now:
            return False, "Invalid or expired reset code."

        stamp = now_iso()
        db.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(new_password), stamp, user["id"]),
        )
        db.execute("UPDATE password_resets SET used_at = ? WHERE id = ?", (stamp, reset["id"]))
    return True, None


init_db()

SYSTEM_PROMPT = """You are Kart, a friendly AI product advisor. Your job is to help users find the best product to buy on Amazon or Walmart.

Have a natural conversation to understand what the user needs. Before triggering a search, make sure you know:
1. The SPECIFIC product — including brand or type if it matters (e.g. "gaming console" → ask PlayStation, Xbox, or Nintendo?)
2. Their budget — ask once if not given; if they already stated a budget earlier in the conversation, carry it forward and do NOT ask again
3. Any key preferences — ask once, keep it optional

FOLLOW-UP SEARCHES (most important rule):
If the user asks for a different product within the same conversation:
- Reuse their budget from earlier unless they change it — do NOT ask for budget again
- If the category is clear and budget is known, go ahead and search immediately
- Only ask a clarifying question if the product type is genuinely ambiguous (e.g. "show me headphones" is clear enough; "show me something for music" is not)
- Never ask more than ONE clarifying question before searching on a follow-up

First-time search rules — ask before searching:
- If the product category is ambiguous, ask to clarify (one question only)
- If no budget has been mentioned at all in the conversation, ask for it
- Do NOT ask for features if you already have product + budget

IMPORTANT — do NOT search until you have both product and budget confirmed. If you asked "PlayStation, Xbox, or Nintendo?" — wait for their reply before triggering [SEARCH].

Search query rules:
- Use all known info: brand, type, features, budget
- Keep store constraints out of the query text (handle them separately)
- Be specific enough to avoid the wrong category
- Bad: [SEARCH: gaming console] — too generic
- Good: [SEARCH: PlayStation 5 console under $1500]
- Good: [SEARCH: best dishwasher machine appliance under $700]
- Good: [SEARCH: Star Wars LEGO set under $70]

When ready, emit exactly:
[SEARCH: <specific query>]

After receiving search results:
- Recommend the best match naturally — name, price, rating, why it fits the user's needs
- NEVER say "let me try again" or reference the search mechanism
- If results are imperfect, recommend the closest match and explain why it still works

Do NOT emit [Waiting for your response] or any bracketed status messages — just speak naturally."""


def get_groq_response(history, max_tokens=512):
    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        temperature=0.7,
        max_tokens=max_tokens
    )
    return completion.choices[0].message.content


def stream_groq_response(history, max_tokens=300):
    """Yield raw text chunks from a streaming Groq completion."""
    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        temperature=0.7,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in completion:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Events data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _strip_internal_tokens(text: str) -> str:
    text = re.sub(r'\[SEARCH:[^\]]*\]', '', text)
    text = re.sub(r'\[Waiting[^\]]*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[Searching[^\]]*\]', '', text, flags=re.IGNORECASE)
    return text.strip()


def _clean_search_query(query):
    query = re.sub(r"[\r\n\t]+", " ", str(query or ""))
    query = re.sub(r"\s+", " ", query).strip(" .,-:;\"'")
    return query[:140]


def _store_mentions(text, store):
    if not text:
        return False

    store_pattern = "wal[- ]?mart" if store == "walmart" else "amazon"
    patterns = [
        rf"\b(?:from|on|at|via|through)\s+(?:the\s+)?{store_pattern}\b",
        rf"\b(?:only|just|specifically|exclusively|prefer(?:ably)?)\s+(?:from|on|at|via|through)?\s*(?:the\s+)?{store_pattern}\b",
        rf"\b{store_pattern}\s+(?:only|specifically|exclusively)\b",
        rf"\bprefer\s+(?:the\s+)?{store_pattern}\b",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def detect_store_preference(*texts):
    """Return a requested marketplace when the user clearly asks for one."""
    joined = " ".join(str(text or "") for text in texts)
    both_stores = r"(?:amazon\s+(?:or|and)\s+wal[- ]?mart|wal[- ]?mart\s+(?:or|and)\s+amazon)"
    if re.search(rf"\b{both_stores}\b", joined, flags=re.IGNORECASE):
        return None

    wants_amazon = _store_mentions(joined, "amazon")
    wants_walmart = _store_mentions(joined, "walmart")

    if wants_amazon and not wants_walmart:
        return "Amazon"
    if wants_walmart and not wants_amazon:
        return "Walmart"
    return None


def strip_store_qualifiers(query):
    """Remove marketplace instructions without removing product brands."""
    original = _clean_search_query(query)
    if not original:
        return ""

    store_pattern = r"(?:amazon|wal[- ]?mart)"
    both_stores = r"(?:amazon\s+(?:or|and)\s+wal[- ]?mart|wal[- ]?mart\s+(?:or|and)\s+amazon)"
    cleaned = re.sub(
        rf"\b(?:only|just|specifically|exclusively|prefer(?:ably)?)?\s*(?:from|on|at|via|through)\s+(?:the\s+)?{both_stores}\b",
        " ",
        original,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"\b(?:only|just|specifically|exclusively|prefer(?:ably)?)\s+(?:from|on|at|via|through)?\s*(?:the\s+)?{store_pattern}\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"\b(?:from|on|at|via|through)\s+(?:the\s+)?{store_pattern}\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"\b{store_pattern}\s+(?:only|specifically|exclusively)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_search_query(cleaned) or original


def _as_list(value):
    if isinstance(value, list):
        items = []
        for v in value:
            if isinstance(v, dict):
                v = v.get("query") or v.get("text") or v.get("value") or ""
            if str(v).strip():
                items.append(str(v).strip())
        return items
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_json_object(text):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _fallback_image_profile(text, hint=""):
    query = _clean_search_query(text)
    if hint:
        query = _clean_search_query(f"{query} {hint}")
    return {
        "primary_query": query or "similar product",
        "brand": "",
        "model": "",
        "product_type": "",
        "visible_text": [],
        "attributes": [],
        "search_queries": [query or "similar product"],
        "confidence": 0.35,
        "uncertainty": "Vision response was not structured.",
    }


def _normalize_image_profile(profile, hint=""):
    if not isinstance(profile, dict):
        return _fallback_image_profile(str(profile), hint)

    normalized = {
        "primary_query": _clean_search_query(profile.get("primary_query")),
        "brand": _clean_search_query(profile.get("brand")),
        "model": _clean_search_query(profile.get("model")),
        "product_type": _clean_search_query(profile.get("product_type")),
        "visible_text": _as_list(profile.get("visible_text")),
        "attributes": _as_list(profile.get("attributes")),
        "search_queries": _as_list(profile.get("search_queries")),
        "confidence": profile.get("confidence", 0.5),
        "uncertainty": str(profile.get("uncertainty", "")).strip(),
    }

    try:
        normalized["confidence"] = max(0.0, min(1.0, float(normalized["confidence"])))
    except Exception:
        normalized["confidence"] = 0.5

    generated = []
    brand = normalized["brand"]
    model = normalized["model"]
    product_type = normalized["product_type"]
    visible_text = normalized["visible_text"]
    attrs = normalized["attributes"][:3]

    if brand and model and product_type:
        generated.append(f"{brand} {model} {product_type}")
    if brand and model:
        generated.append(f"{brand} {model}")
    if visible_text:
        generated.append(" ".join(visible_text[:3]))
    if brand and product_type:
        generated.append(f"{brand} {product_type} {' '.join(attrs)}")
    if normalized["primary_query"]:
        generated.append(normalized["primary_query"])
    if hint:
        generated.append(f"{normalized['primary_query']} {hint}")

    queries = []
    seen = set()
    for query in normalized["search_queries"] + generated:
        cleaned = _clean_search_query(query)
        key = cleaned.lower()
        if cleaned and key not in seen:
            queries.append(cleaned)
            seen.add(key)

    if not normalized["primary_query"]:
        normalized["primary_query"] = queries[0] if queries else "similar product"

    normalized["search_queries"] = queries[:MAX_IMAGE_SEARCH_QUERIES] or [normalized["primary_query"]]
    return normalized


def image_to_search_profile(image_bytes, mime_type, hint=""):
    """Use Groq vision to identify an exact product and produce search variants."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set.")

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "Identify the main purchasable product for exact shopping search. "
        "Prioritize visible brand names, model numbers, label text, packaging text, "
        "shape, color, size, material, and distinguishing features. "
        "Return valid JSON only with these keys: primary_query, brand, model, "
        "product_type, visible_text, attributes, search_queries, confidence, uncertainty. "
        "search_queries must contain 3 to 5 Amazon-style queries ordered from most "
        "exact to broadest. If brand/model text is visible, put that in the first query. "
        "Do not guess a brand or model unless it is visible."
    )
    if hint:
        prompt += f"\nUser hint: {hint[:160]}"

    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}"
                        }
                    }
                ],
            }
        ],
        temperature=0.2,
        max_tokens=420,
    )

    content = completion.choices[0].message.content.strip()
    try:
        profile = _extract_json_object(content)
    except Exception:
        profile = _fallback_image_profile(content, hint)
    return _normalize_image_profile(profile, hint)


def image_to_search_query(image_bytes, mime_type, hint=""):
    """Backward-compatible wrapper for callers that only need one query."""
    return image_to_search_profile(image_bytes, mime_type, hint)["primary_query"]


def extract_search_query(text):
    match = re.search(r'\[SEARCH:\s*(.+?)\]', text)
    return match.group(1).strip() if match else None


def search_all_platforms(query, preferred_source=None, budget=None):
    """Search the requested marketplace, or both Amazon and Walmart."""
    all_results = []
    providers = {
        "Amazon": search_products,
        "Walmart": search_walmart_products,
    }

    if preferred_source in providers:
        providers = {preferred_source: providers[preferred_source]}

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {
            executor.submit(search_fn, query, budget): platform
            for platform, search_fn in providers.items()
        }
        for future in as_completed(futures):
            platform = futures[future]
            try:
                results = future.result()
                all_results.extend(results or [])
            except Exception as e:
                print(f"{platform} search failed: {e}")
    return all_results


def parse_price(price_str):
    """Extract a float from price strings like '$299.99', '1,299.00', etc."""
    if not price_str or price_str in ("N/A", "—", ""):
        return None
    try:
        cleaned = re.sub(r'[^\d.]', '', str(price_str))
        return float(cleaned) if cleaned else None
    except Exception:
        return None


def extract_budget(query):
    """Pull the dollar amount from a query like 'PlayStation 5 under $1500'."""
    match = re.search(r'\$?([\d,]+)', query)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except Exception:
            return None
    return None


def bayesian_rating(rating, num_reviews, m=200, c=4.0):
    """
    IMDb-style Bayesian weighted rating.
    Pulls a product's rating toward the global mean (c) when it has few reviews.
      m = minimum review threshold for full trust
      c = assumed global mean rating
    A product with 5.0 stars but only 8 reviews will score lower than
    a product with 4.5 stars and 3 000 reviews.
    """
    v = max(int(num_reviews or 0), 0)
    r = float(rating or 0)
    return (v / (v + m)) * r + (m / (v + m)) * c


def rank_products(products, query):
    query_lower = query.lower()
    budget = extract_budget(query)

    # Compute median product price to detect when budget is way above category range
    prices = [parse_price(p.get("price")) for p in products]
    prices = [p for p in prices if p is not None and p > 0]
    if prices:
        prices_sorted = sorted(prices)
        mid = len(prices_sorted) // 2
        median_price = (prices_sorted[mid] + prices_sorted[~mid]) / 2
    else:
        median_price = None

    # Treat the budget as irrelevant only when it is wildly unrealistic —
    # more than 10× the median category price (e.g. $100,000 for a backpack).
    # A reasonable premium budget like $200 vs a $60 median should still
    # influence ranking so higher-quality options surface.
    budget_relevant = (
        budget is not None
        and budget > 50
        and median_price is not None
        and budget <= median_price * 10
    )

    ranked = []
    for p in products:
        # Bayesian weighted rating (accounts for review volume)
        try:
            rating = float(p.get("rating") or 0)
        except Exception:
            rating = 0
        num_reviews = int(p.get("num_reviews") or 0)
        w_rating = bayesian_rating(rating, num_reviews)

        # Keyword relevance
        name = (p.get("name") or "").lower()
        relevance = 1 if any(w in name for w in query_lower.split()) else 0

        # Budget-fit scoring — rewards products that make good use of the
        # stated budget without heavily penalising cheaper options.
        price_score = 0.0
        if budget_relevant:
            price = parse_price(p.get("price"))
            if price is not None:
                ratio = price / budget
                if ratio > 1.0:
                    # Over budget — penalise proportionally
                    price_score = -1.5 * (ratio - 1.0)
                elif ratio >= 0.50:
                    # Sweet spot: using 50–100% of budget → strong reward
                    price_score = 0.6 * ratio
                elif ratio >= 0.25:
                    # Moderate use of budget → small reward
                    price_score = 0.3 * ratio
                elif ratio < 0.10:
                    # Way below budget — likely wrong category
                    price_score = -1.5

        score = (w_rating * 0.70) + (relevance * 0.15) + price_score
        ranked.append((score, p))

    ranked.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in ranked]


def _normalize_match_text(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_match_text(text):
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _match_tokens(text):
    return {
        token
        for token in _normalize_match_text(text).split()
        if len(token) > 1 and token not in SEARCH_STOP_WORDS
    }


def _image_profile_text(profile):
    parts = [
        profile.get("primary_query", ""),
        profile.get("brand", ""),
        profile.get("model", ""),
        profile.get("product_type", ""),
        " ".join(profile.get("visible_text", [])),
        " ".join(profile.get("attributes", [])),
    ]
    return " ".join(parts)


def _product_dedupe_key(product):
    source = str(product.get("source") or "").lower()
    product_id = product.get("asin") or product.get("product_id") or product.get("us_item_id")
    if product_id:
        return f"{source}:id:{product_id}"

    link = str(product.get("link") or "").split("?")[0].rstrip("/")
    if link and link != "#":
        return f"{source}:link:{link.lower()}"

    return f"{source}:name:{_normalize_match_text(product.get('name'))}"


def _clean_image_url(value):
    if isinstance(value, list):
        for item in value:
            cleaned = _clean_image_url(item)
            if cleaned:
                return cleaned
        return ""
    if isinstance(value, dict):
        for key in ("url", "image", "image_url", "thumbnail", "thumbnail_url"):
            cleaned = _clean_image_url(value.get(key))
            if cleaned:
                return cleaned
        return ""

    url = str(value or "").strip()
    if url.startswith(("http://", "https://", "data:image/")):
        return url
    return ""


def _displayable_products(products):
    displayable = []
    for product in products:
        name = str(product.get("name") or "").strip()
        if not name or name.upper() == "N/A":
            continue

        item = dict(product)
        item["name"] = name
        item["image"] = _clean_image_url(item.get("image"))
        displayable.append(item)

    return displayable


def _dedupe_products(products):
    deduped = {}
    for product in products:
        key = _product_dedupe_key(product)
        existing = deduped.get(key)
        if not existing:
            item = dict(product)
            item["_matched_queries"] = [product.get("_matched_query")] if product.get("_matched_query") else []
            deduped[key] = item
            continue

        if product.get("_matched_query"):
            existing.setdefault("_matched_queries", []).append(product["_matched_query"])
        existing["_query_rank"] = min(existing.get("_query_rank", 99), product.get("_query_rank", 99))
        existing["_provider_rank"] = min(existing.get("_provider_rank", 99), product.get("_provider_rank", 99))

    return list(deduped.values())


def search_image_query_variants(profile, preferred_source=None):
    """Run several exact-to-broad searches and merge the product results."""
    raw_queries = profile.get("search_queries") or [profile.get("primary_query", "similar product")]
    queries = []
    seen = set()
    for query in raw_queries:
        cleaned = strip_store_qualifiers(query)
        key = cleaned.lower()
        if cleaned and key not in seen:
            queries.append(cleaned)
            seen.add(key)
    queries = queries or ["similar product"]
    all_results = []

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(queries)))) as executor:
        futures = {
            executor.submit(search_all_platforms, query, preferred_source): (i, query)
            for i, query in enumerate(queries)
        }
        for future in as_completed(futures):
            query_rank, query = futures[future]
            try:
                for provider_rank, product in enumerate(future.result() or []):
                    item = dict(product)
                    item["_matched_query"] = query
                    item["_query_rank"] = query_rank
                    item["_provider_rank"] = provider_rank
                    all_results.append(item)
            except Exception as e:
                print(f"Image query failed for '{query}': {e}")

    return _dedupe_products(all_results)


def image_match_score(product, profile):
    """Score exact product identity before quality/rating signals."""
    name = product.get("name") or ""
    name_norm = _normalize_match_text(name)
    name_compact = _compact_match_text(name)
    primary_norm = _normalize_match_text(profile.get("primary_query"))
    profile_tokens = _match_tokens(_image_profile_text(profile))
    name_tokens = _match_tokens(name)
    overlap = profile_tokens & name_tokens

    coverage = len(overlap) / max(len(profile_tokens), 1)
    precision = len(overlap) / max(len(name_tokens), 1)
    similarity = SequenceMatcher(None, primary_norm, name_norm).ratio() if primary_norm and name_norm else 0

    score = (coverage * 7.0) + (precision * 2.0) + (similarity * 3.0)

    brand = _normalize_match_text(profile.get("brand"))
    model = _normalize_match_text(profile.get("model"))
    product_type = _normalize_match_text(profile.get("product_type"))
    strict_profile = profile.get("confidence", 0.5) >= 0.55

    if brand:
        score += 3.0 if _compact_match_text(brand) in name_compact else (-2.0 if strict_profile else -0.5)
    if model:
        score += 4.0 if _compact_match_text(model) in name_compact else (-1.5 if strict_profile else -0.3)
    if product_type:
        type_tokens = _match_tokens(product_type)
        if type_tokens:
            score += 1.5 * (len(type_tokens & name_tokens) / len(type_tokens))

    for text in profile.get("visible_text", [])[:4]:
        text_norm = _normalize_match_text(text)
        text_compact = _compact_match_text(text)
        if len(text_norm) >= 3 and (text_norm in name_norm or text_compact in name_compact):
            score += 2.0

    query_rank = product.get("_query_rank", 99)
    provider_rank = product.get("_provider_rank", 99)
    score += max(0.0, 1.8 - (query_rank * 0.35))
    score += max(0.0, 1.2 - (provider_rank * 0.12))

    try:
        rating = float(product.get("rating") or 0)
    except Exception:
        rating = 0
    score += min(max(rating, 0), 5) * 0.12

    reviews = int(product.get("num_reviews") or 0)
    score += min(reviews, 5000) / 5000 * 0.35

    if product.get("source") == "Amazon":
        score += 0.15

    return score


def rank_image_products(products, profile):
    ranked = []
    for product in products:
        score = image_match_score(product, profile)
        item = dict(product)
        item["match_score"] = round(score, 3)
        ranked.append((score, item))

    ranked.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in ranked]


def prune_search_context(history):
    """
    Remove previous search-result injections from history so that a new
    product search starts with a clean slate.  Conversational turns
    (clarifying questions, budget discussions) are kept so the bot still
    knows what the user wants.
    """
    cleaned = []
    for msg in history:
        # Drop the injected "[Search results: …]" user turns
        if msg["role"] == "user" and msg["content"].startswith("[Search results:"):
            continue
        cleaned.append(msg)
    return cleaned


def format_for_llm(products):
    lines = []
    for i, p in enumerate(products[:RECOMMENDATION_COUNT], 1):
        reviews = p.get("num_reviews")
        review_str = f" | Reviews: {reviews:,}" if reviews else ""
        lines.append(f"{i}. {p['name']} | Rating: {p['rating']}{review_str} | Price: {p['price']}")
    return "\n".join(lines)


def apply_sentiment(products, resort=True):
    """
    Run DistilBERT sentiment on each product's review blurb (or name as fallback).
    Attaches a 'sentiment' score and re-sorts by a combined rating+sentiment signal.
    """
    texts = [p.get("review") or p.get("name") or "" for p in products]
    scores = score_batch(texts)

    for p, s in zip(products, scores):
        p["sentiment"] = s

    # Re-rank: blend existing rating with sentiment confidence
    def combined(p):
        try:
            rating = float(p.get("rating") or 0) / 5.0   # normalise to 0-1
        except Exception:
            rating = 0
        sentiment = p.get("sentiment", 0.5)
        return (rating * 0.65) + (sentiment * 0.35)

    if resort:
        products.sort(key=combined, reverse=True)
    return products


def prepare_product_results(query, preferred_source=None):
    """Search, rank, review, and sentiment-score products for a query."""
    search_query = strip_store_qualifiers(query)
    budget = extract_budget(query)
    raw = _displayable_products(search_all_platforms(search_query, preferred_source, budget=budget))
    if not raw:
        return []

    ranked = rank_products(raw, search_query)[:RECOMMENDATION_COUNT]
    ranked = generate_reviews(ranked)
    ranked = apply_sentiment(ranked)
    return ranked[:RECOMMENDATION_COUNT]


def prepare_image_product_results(profile, preferred_source=None):
    """Search multiple image-derived queries and preserve exact-match ranking."""
    raw = _displayable_products(search_image_query_variants(profile, preferred_source))
    if not raw:
        return []

    ranked = rank_image_products(raw, profile)[:RECOMMENDATION_COUNT]
    ranked = generate_reviews(ranked)
    ranked = apply_sentiment(ranked, resort=False)
    return ranked[:RECOMMENDATION_COUNT]


def generate_reviews(products):
    """Ask Groq to produce a one-sentence review blurb for each product."""
    if not GROQ_API_KEY or not products:
        return products

    product_lines = "\n".join(
        f"{i+1}. {p['name']} | Rating: {p['rating']} | Price: {p['price']}"
        for i, p in enumerate(products)
    )
    prompt = (
        f"For each product write ONE sentence (max 12 words) on what customers love.\n"
        f"Products:\n{product_lines}\n"
        f"Reply ONLY numbered 1-{len(products)}, one per line."
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150
        )
        lines = completion.choices[0].message.content.strip().split("\n")
        reviews = [re.sub(r'^\d+[\.\)]\s*', '', l.strip()) for l in lines if l.strip()]
        for i, p in enumerate(products):
            if i < len(reviews) and reviews[i]:
                p["review"] = reviews[i]
    except Exception:
        pass  # reviews are optional — never break the main flow

    return products


@app.route("/")
def home():
    return render_template("index.html")


def payload_int(payload, key):
    try:
        value = payload.get(key)
        return int(value) if value not in (None, "") else None
    except Exception:
        return None


@app.route("/api/bootstrap")
def api_bootstrap():
    session.pop("active_user_id", None)
    session.pop("active_chat_id", None)
    session.pop("anonymous_chat_id", None)
    return jsonify(auth_payload())


@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    data = request.get_json(silent=True) or {}
    user_id, error = create_account(data.get("name"), data.get("email"), data.get("password"))
    if error:
        return jsonify({"error": error}), 400

    set_login_session(user_id)
    return jsonify(auth_payload(user_id))


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    user = authenticate_user(data.get("email"), data.get("password"))
    if not user:
        return jsonify({"error": "Invalid email or password."}), 401

    set_login_session(user["id"])
    return jsonify(auth_payload(user["id"]))


@app.route("/api/auth/request-reset", methods=["POST"])
def api_request_password_reset():
    data = request.get_json(silent=True) or {}
    user = get_user_by_email(data.get("email"))
    response = {
        "message": "If that email has an account, a reset code has been sent.",
        "reset_delivery": "email",
    }

    if user and not user.get("is_anonymous") and user.get("password_hash"):
        token, _ = create_password_reset(user["id"])
        email_sent = send_password_reset_email(user, token)
        if not email_sent:
            if ALLOW_DEV_RESET_CODE or is_local_request():
                response["reset_delivery"] = "local"
                response["message"] = "Email is not configured, so a local reset code was filled in for testing."
                response["dev_reset_code"] = token
            else:
                response["reset_delivery"] = "unavailable"
                response["message"] = "Password reset email is not configured yet."

    return jsonify(response)


@app.route("/api/auth/reset-password", methods=["POST"])
def api_reset_password():
    data = request.get_json(silent=True) or {}
    ok, error = reset_password_with_token(
        data.get("email"),
        data.get("token"),
        data.get("password"),
    )
    if not ok:
        return jsonify({"error": error}), 400

    return jsonify({"message": "Password updated. You can log in now."})


@app.route("/api/auth/delete-account", methods=["POST"])
def api_delete_account():
    user_id = current_profile_user_id()
    if not user_id:
        return jsonify({"error": "Please log in to delete your account."}), 401

    data = request.get_json(silent=True) or {}
    user = get_user(user_id)
    if not verify_password(data.get("password"), user.get("password_hash")):
        return jsonify({"error": "Password is incorrect."}), 401

    with get_db() as db:
        db.execute(
            "DELETE FROM result_sets WHERE chat_id IN (SELECT id FROM chats WHERE user_id = ?)",
            (user_id,),
        )
        db.execute(
            "DELETE FROM messages WHERE chat_id IN (SELECT id FROM chats WHERE user_id = ?)",
            (user_id,),
        )
        db.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM chats WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))

    clear_login_session()
    return jsonify(auth_payload())


@app.route("/api/users", methods=["POST"])
def api_create_user():
    return jsonify({"error": "Use secure account signup."}), 400


@app.route("/api/users/select", methods=["POST"])
def api_select_user():
    return jsonify({"error": "Use email and password login."}), 400


@app.route("/api/chats", methods=["POST"])
def api_create_chat():
    user_id = current_profile_user_id()
    if not user_id:
        return jsonify({"error": "Please log in to save chats."}), 401

    session["active_user_id"] = user_id
    chat_id = create_chat(user_id)
    session["active_chat_id"] = chat_id
    return jsonify({
        "chat_id": chat_id,
        "active_user_id": user_id,
        "authenticated": True,
        "user": public_user(get_user(user_id)),
        "chats": list_chats(user_id),
        "detail": chat_detail(chat_id),
    })


@app.route("/api/chats/<int:chat_id>")
def api_chat_detail(chat_id):
    user_id = current_profile_user_id()
    if not user_id:
        return jsonify({"error": "Please log in to view chat history."}), 401

    chat = get_chat(chat_id, user_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404
    session["active_chat_id"] = chat_id
    return jsonify({
        "active_chat_id": chat_id,
        "active_user_id": user_id,
        "authenticated": True,
        "user": public_user(get_user(user_id)),
        "chats": list_chats(user_id),
        "detail": chat_detail(chat_id),
    })


@app.route("/api/chats/<int:chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    user_id = current_profile_user_id()
    if not user_id:
        return jsonify({"error": "Please log in to delete chats."}), 401

    chat = get_chat(chat_id, user_id)
    if not chat:
        return jsonify({"error": "Chat not found."}), 404

    with get_db() as db:
        db.execute("DELETE FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id))

    if session.get("active_chat_id") == chat_id:
        session.pop("active_chat_id", None)

    return jsonify({
        "active_user_id": user_id,
        "active_chat_id": None,
        "authenticated": True,
        "user": public_user(get_user(user_id)),
        "chats": list_chats(user_id),
        "detail": empty_chat_detail(),
    })


@app.route("/api/auth/logout", methods=["POST"])
@app.route("/api/logout", methods=["POST"])
def api_logout():
    clear_login_session()
    return jsonify(auth_payload())


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    profile_user_id = current_profile_user_id(payload_int(data, "user_id"))
    is_authenticated = bool(profile_user_id)
    if is_authenticated:
        user_id = profile_user_id
        session["active_user_id"] = user_id
        chat_id = resolve_chat_id(user_id, payload_int(data, "chat_id"), session_key="active_chat_id")
    else:
        user_id = ensure_anonymous_user()
        requested_chat_id = payload_int(data, "chat_id")
        if requested_chat_id:
            chat_id = resolve_chat_id(user_id, requested_chat_id, session_key="anonymous_chat_id")
        else:
            chat_id = create_chat(user_id)
            session["anonymous_chat_id"] = chat_id

    if not GROQ_API_KEY:
        fallback = "GROQ_API_KEY is not set. Please add it to your .env file."
        add_message(chat_id, "user", user_message)
        add_message(chat_id, "assistant", fallback)
        maybe_update_chat_title(chat_id, user_message)
        return jsonify({"error": fallback, "chat_id": chat_id})

    history = public_message_history(chat_id)
    add_message(chat_id, "user", user_message)
    maybe_update_chat_title(chat_id, user_message)

    # Capture all values needed inside the generator (request context closes after return)
    _chat_id        = chat_id
    _user_id        = user_id
    _is_auth        = is_authenticated
    _user_message   = user_message
    _history        = history

    @stream_with_context
    def generate():
        # ── Phase 1: non-streaming call to detect [SEARCH:] ──────────────────
        first_response  = get_groq_response(_history + [{"role": "user", "content": _user_message}])
        search_query    = extract_search_query(first_response)
        preferred_src   = detect_store_preference(_user_message, search_query)
        display         = _strip_internal_tokens(first_response)

        if not search_query:
            # ── Conversational turn — emit full text as one chunk ─────────────
            yield _sse({"type": "text", "content": display})
            add_message(_chat_id, "assistant", display)
            yield _sse({
                "type": "done",
                "chat_id": _chat_id,
                "authenticated": _is_auth,
                "chats": list_chats(_user_id) if _is_auth else [],
            })
            return

        # ── Phase 2: product search ───────────────────────────────────────────
        yield _sse({"type": "searching"})

        effective_query = strip_store_qualifiers(search_query)
        ranked          = prepare_product_results(effective_query, preferred_src)

        if not ranked:
            source_note = f" on {preferred_src}" if preferred_src else ""
            msg = f"Hmm, I couldn't find results{source_note} for that. Could you describe it differently?"
            yield _sse({"type": "text", "content": msg})
            add_message(_chat_id, "assistant", msg)
            yield _sse({"type": "done", "chat_id": _chat_id, "authenticated": _is_auth,
                        "chats": list_chats(_user_id) if _is_auth else []})
            return

        # ── Phase 3: stream the recommendation ───────────────────────────────
        results_text       = format_for_llm(ranked)
        source_note        = f" from {preferred_src}" if preferred_src else ""
        source_instruction = (
            f"Only recommend products from {preferred_src}."
            if preferred_src else "Recommend the best product from these results."
        )
        source_instruction += (
            " Write your recommendation naturally. "
            "Do NOT include any [SEARCH:] tokens, do NOT suggest searching again, "
            "and do NOT say the results didn't match — just recommend the best option available."
        )
        final_history = _history + [
            {"role": "user",      "content": _user_message},
            {"role": "assistant", "content": display or "Let me search for that."},
            {"role": "user",      "content": f"[Search results{source_note} for: {effective_query}\n{results_text}]\n\n{source_instruction}"},
        ]

        # Accumulate the full response before emitting so that [SEARCH:] tokens
        # that span multiple chunks are reliably stripped from the complete text.
        raw_final = ""
        for chunk in stream_groq_response(final_history, max_tokens=300):
            raw_final += chunk

        full_final = _strip_internal_tokens(raw_final)

        # Emit word-by-word for the streaming typewriter effect
        words = full_final.split(" ")
        for i, word in enumerate(words):
            piece = word + (" " if i < len(words) - 1 else "")
            yield _sse({"type": "text", "content": piece})

        full_final = full_final.strip()

        # ── Store and emit products ───────────────────────────────────────────
        result_source = preferred_src or "text"
        result_id     = add_result_set(_chat_id, result_source, effective_query, full_final, ranked)
        result_set    = {
            "id": result_id, "chat_id": _chat_id, "source": result_source,
            "query": effective_query, "response": full_final,
            "products": ranked, "created_at": now_iso(),
        }
        add_message(_chat_id, "assistant", full_final)

        yield _sse({"type": "products", "products": ranked, "query": effective_query,
                    "preferred_source": preferred_src, "result_set": result_set})
        yield _sse({"type": "done", "chat_id": _chat_id, "authenticated": _is_auth,
                    "chats": list_chats(_user_id) if _is_auth else []})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/image-search", methods=["POST"])
def image_search():
    if "image" not in request.files:
        return jsonify({"error": "Please upload an image."}), 400

    try:
        requested_user_id = int(request.form.get("user_id")) if request.form.get("user_id") else None
    except Exception:
        requested_user_id = None

    profile_user_id = current_profile_user_id(requested_user_id)
    is_authenticated = bool(profile_user_id)
    if is_authenticated:
        user_id = profile_user_id
        session["active_user_id"] = user_id
        chat_id = resolve_chat_id(user_id, request.form.get("chat_id"), session_key="active_chat_id")
    else:
        user_id = ensure_anonymous_user()
        requested_chat_id = request.form.get("chat_id")
        if requested_chat_id:
            chat_id = resolve_chat_id(user_id, requested_chat_id, session_key="anonymous_chat_id")
        else:
            chat_id = create_chat(user_id)
            session["anonymous_chat_id"] = chat_id

    image = request.files["image"]
    hint = request.form.get("hint", "").strip()
    mime_type = image.mimetype or ""

    if mime_type not in ALLOWED_IMAGE_TYPES:
        return jsonify({"error": "Please upload a JPG, PNG, WEBP, or GIF image."}), 400

    image_bytes = image.read()
    if not image_bytes:
        return jsonify({"error": "The uploaded image was empty."}), 400
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return jsonify({"error": "Please upload an image smaller than 3 MB."}), 400

    user_text = hint or "Search from this image"
    preferred_source = detect_store_preference(hint)
    add_message(chat_id, "user", user_text)
    maybe_update_chat_title(chat_id, user_text)

    try:
        profile = image_to_search_profile(image_bytes, mime_type, hint)
        query = profile["primary_query"]
        products = prepare_image_product_results(profile, preferred_source)
    except Exception as e:
        print(f"Image search failed: {e}")
        response = "I could not analyze that image. Please try another one."
        add_message(chat_id, "assistant", response)
        return jsonify({"error": response, "chat_id": chat_id}), 500

    if not products:
        query_list = ", ".join(profile.get("search_queries", [])[:3])
        source_note = f" on {preferred_source}" if preferred_source else ""
        response = f"I identified this as: {query}\n\nI tried these searches: {query_list}. I couldn't find a close product match{source_note}. Try adding the brand, model number, or any label text you can see."
        add_message(chat_id, "assistant", response)
        return jsonify({
            "response": response,
            "query": query,
            "queries": profile.get("search_queries", []),
            "products": [],
            "preferred_source": preferred_source,
            "chat_id": chat_id,
            "authenticated": is_authenticated,
            "chats": list_chats(user_id) if is_authenticated else [],
        })

    confidence_note = ""
    if profile.get("confidence", 1) < 0.55:
        confidence_note = "\n\nThe image was a little ambiguous, so adding visible brand/model text can improve the match."

    source_note = f" on {preferred_source}" if preferred_source else ""
    response = f"I identified this as: {query}\n\nI searched several exact-match variants{source_note} and ranked the closest title matches first.{confidence_note}"
    add_message(chat_id, "assistant", response)
    result_source = f"image {preferred_source}" if preferred_source else "image"
    result_id = add_result_set(chat_id, result_source, query, response, products)
    result_set = {
        "id": result_id,
        "chat_id": chat_id,
        "source": result_source,
        "query": query,
        "response": response,
        "products": products,
        "created_at": now_iso(),
    }

    return jsonify({
        "response": response,
        "query": query,
        "queries": profile.get("search_queries", []),
        "products": products,
        "preferred_source": preferred_source,
        "result_set": result_set,
        "chat_id": chat_id,
        "authenticated": is_authenticated,
        "chats": list_chats(user_id) if is_authenticated else [],
    })


def check_sentiment_model():
    """Run a quick sanity check on the DistilBERT model at startup."""
    print("\n--- DistilBERT Sentiment Check ---")
    try:
        results = score_batch(["This product is absolutely amazing and works perfectly"])
        score = results[0]
        if score != 0.5:
            print(f"DistilBERT is ACTIVE - test score: {score}")
        else:
            print("DistilBERT returned 0.5 (neutral fallback) - model may not be loaded.")
    except Exception as e:
        print(f"DistilBERT check failed: {e}")
    print("----------------------------------\n")


if __name__ == "__main__":
    check_sentiment_model()
    app.run(debug=True)
