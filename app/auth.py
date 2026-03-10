from fastapi import Request, Response, HTTPException, Depends
from sqlalchemy.orm import Session
import redis
import secrets
import bcrypt
import json
import time

from database import get_db
from models import User

# Redis для сессий
r = redis.Redis(host="localhost", port=6379, decode_responses=True)
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

    r.setex(token, SESSION_TTL, json.dumps(session_data))
    return token


def get_session(token):
    data = r.get(token)
    if not data:
        return None
    return json.loads(data)


def save_session(token, session_data):
    r.setex(token, SESSION_TTL, json.dumps(session_data))


def delete_session(token):
    r.delete(token)


def init_auth(app):
    # REGISTER
    @app.post("/register")
    async def register(request: Request, db: Session = Depends(get_db)):
        data = await request.json()
        email = data["email"]
        password = data["password"]

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
    async def login(request: Request, response: Response, db: Session = Depends(get_db)):
        data = await request.json()
        email = data["email"]
        password = data["password"]

        user = db.query(User).filter(User.email == email).first()

        if not user:
            raise HTTPException(status_code=401)

        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            raise HTTPException(status_code=401)

        # защита от session fixation
        old_token = request.cookies.get("session_token")
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
    async def chat(request: Request):
        token = request.cookies.get("session_token")

        if not token:
            raise HTTPException(status_code=401)

        session = get_session(token)

        if not session or not session["authenticated"]:
            raise HTTPException(status_code=403)

        data = await request.json()
        message = data.get("message", "")

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
