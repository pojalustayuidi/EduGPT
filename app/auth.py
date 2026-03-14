from fastapi import Request, Response, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import redis
import secrets
import bcrypt
import json
import time
import os

from app.database import get_db
from app.models import User


# Pydantic модели для запросов
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChatRequest(BaseModel):
    message: str


# Redis для сессий - БЕРЁМ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=3
    )
    r.ping()
    print(f"Redis подключен к {REDIS_HOST}:{REDIS_PORT}")
    REDIS_AVAILABLE = True
except Exception as e:
    print(f"Redis не доступен: {e}")
    REDIS_AVAILABLE = False
    # Запасной вариант - словарь в памяти
    sessions_store = {}

SESSION_TTL = 60 * 60 * 24


def generate_token():
    return secrets.token_hex(32)


def create_session(user_id=None):
    token = generate_token()
    session_data = {
        "user_id": user_id,
        "authenticated": bool(user_id),
        "created_at": time.time(),
        "history": []
    }

    if REDIS_AVAILABLE:
        r.setex(token, SESSION_TTL, json.dumps(session_data))
    else:
        sessions_store[token] = session_data

    return token


def get_session(token):
    if REDIS_AVAILABLE:
        data = r.get(token)
        if not data:
            return None
        return json.loads(data)
    else:
        return sessions_store.get(token)


def save_session(token, session_data):
    if REDIS_AVAILABLE:
        r.setex(token, SESSION_TTL, json.dumps(session_data))
    else:
        sessions_store[token] = session_data


def delete_session(token):
    if REDIS_AVAILABLE:
        r.delete(token)
    else:
        if token in sessions_store:
            del sessions_store[token]


def init_auth(app):
    # REGISTER
    @app.post("/register")
    async def register(
            body: RegisterRequest,
            db: Session = Depends(get_db)
    ):
        email = body.email
        password = body.password

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        user = User(
            email=email,
            password_hash=password_hash
        )

        db.add(user)

        try:
            db.commit()
        except:
            db.rollback()
            raise HTTPException(status_code=400, detail="User already exists")

        return {"message": "User created"}

    # LOGIN
    @app.post("/login")
    async def login(
            http_request: Request,
            body: LoginRequest,
            response: Response,
            db: Session = Depends(get_db)
    ):
        email = body.email
        password = body.password

        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise HTTPException(status_code=401)

        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            raise HTTPException(status_code=401)

        # защита от session fixation
        old_token = http_request.cookies.get("session_token")
        if old_token:
            delete_session(old_token)

        token = create_session(user.id)

        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=False,
            samesite="Lax"
        )

        return {"message": "Logged in"}

    # LOGOUT
    @app.post("/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get("session_token")

        if token:
            delete_session(token)

        response.delete_cookie("session_token")

        return {"message": "Logged out"}

    # PROTECTED CHAT
    @app.post("/chat")
    async def chat(
            body: ChatRequest,
            http_request: Request
    ):
        token = http_request.cookies.get("session_token")

        if not token:
            raise HTTPException(status_code=401)

        session = get_session(token)

        if not session or not session["authenticated"]:
            raise HTTPException(status_code=403)

        message = body.message

        session["history"].append({
            "role": "user",
            "content": message
        })

        ai_reply = f"Ответ по теме: {message}"

        session["history"].append({
            "role": "assistant",
            "content": ai_reply
        })

        save_session(token, session)

        return {"reply": ai_reply}