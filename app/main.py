# main.py

import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from typing import List, Optional

# Load environment variables
load_dotenv()

# --- Configuration & Initialization ---
app = FastAPI()

# CORS Middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Your Qwik frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GNews API Key Management
GNEWS_API_KEYS = [
    os.getenv(f"GNEWS_API_KEY_{i}") for i in range(1, 6)
    if os.getenv(f"GNEWS_API_KEY_{i}")
]
current_api_key_index = 0

def get_gnews_api_key():
    """Rotates through the available GNews API keys."""
    global current_api_key_index
    if not GNEWS_API_KEYS:
        raise HTTPException(status_code=500, detail="GNews API keys not configured.")
    
    key = GNEWS_API_KEYS[current_api_key_index]
    current_api_key_index = (current_api_key_index + 1) % len(GNEWS_API_KEYS)
    return key

# Supabase Client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# --- Pydantic Models (Data Schemas) ---
class UserAuth(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class NewsArticle(BaseModel):
    title: str
    description: str
    content: Optional[str] = None
    url: str
    image: Optional[str] = None
    publishedAt: Optional[str] = None

# --- API Endpoints ---

# Helper function to fetch from GNews
def fetch_gnews(endpoint: str, params: dict):
    api_key = get_gnews_api_key()
    base_url = "https://gnews.io/api/v4"
    params["apikey"] = api_key
    
    try:
        response = requests.get(f"{base_url}/{endpoint}", params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Error fetching from GNews: {e}")

@app.get("/api/news/top-headlines")
def get_top_headlines(page: int = 1, lang: str = 'en'):
    params = {
        "lang": lang,
        "max": 9, # 3 cards x 3 rows = 9 per page
        "page": page
    }
    return fetch_gnews("top-headlines", params)

@app.get("/api/news/category/{category_name}")
def get_news_by_category(category_name: str, page: int = 1, lang: str = 'en'):
    # GNews categories: general, world, nation, business, technology, entertainment, sports, science, health
    params = {
        "topic": category_name.lower(),
        "lang": lang,
        "max": 9,
        "page": page
    }
    return fetch_gnews("top-headlines", params)

@app.get("/api/news/search")
def search_news(q: str, page: int = 1, lang: str = 'en'):
    if not q:
        raise HTTPException(status_code=400, detail="Search query parameter 'q' is required.")
    params = {
        "q": q,
        "lang": lang,
        "max": 9,
        "page": page,
        "sortby": "publishedAt"
    }
    return fetch_gnews("search", params)

# --- User Authentication Endpoints ---
@app.post("/api/auth/signup")
def signup(user_credentials: UserAuth):
    try:
        signup_data = {
            "email": user_credentials.email,
            "password": user_credentials.password,
        }
        if user_credentials.name:
            signup_data["options"] = {
                "data": {
                    "name": user_credentials.name
                }
            }
        user = supabase.auth.sign_up(signup_data)
        return {"user": user.user, "session": user.session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
def login(user_credentials: UserAuth):
    try:
        user = supabase.auth.sign_in_with_password({
            "email": user_credentials.email,
            "password": user_credentials.password,
        })
        return {"user": user.user, "session": user.session}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid login credentials.")

# --- You would add more endpoints here for saved news and history ---
# Example for getting saved news (requires user to be authenticated on the frontend)
from fastapi import Header

@app.get("/api/user/saved")
def get_saved_news(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    try:
        user = supabase.auth.get_user(token)
        user_id = user.user.id
        data = supabase.table('savednews').select("*").eq('user_id', user_id).execute()
        return data.data
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/api/user/history")
def get_user_history(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    try:
        user = supabase.auth.get_user(token)
        user_id = user.user.id
        data = supabase.table('history').select("*").eq('user_id', user_id).execute()
        return data.data
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/user/saved")
def save_article(article: NewsArticle, authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    try:
        print(f"Saving article for token: {token}")
        user = supabase.auth.get_user(token)
        user_id = user.user.id
    except Exception as e:
        print(f"Error getting user: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        record = article.dict()
        record['user_id'] = user_id
        print(f"Article record to save: {record}")
        result = supabase.table('savednews').insert(record).execute()
        print(f"Insert result: {result}")
        return {"message": "Article saved"}
    except Exception as e:
        print(f"Error saving article: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save article: {str(e)}")

@app.post("/api/user/history")
def add_to_history(article: NewsArticle, authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1] if " " in authorization else authorization
    try:
        user = supabase.auth.get_user(token)
        user_id = user.user.id
        record = article.dict()
        record['user_id'] = user_id
        result = supabase.table('history').insert(record).execute()
        print(f"Insert history result: {result}")
        return {"message": "Article added to history"}
    except Exception as e:
        print(f"Error adding to history: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

#  Test endpoint to check saved articles
@app.get("/api/test/saved")
def test_saved_articles():
    try:
        data = supabase.table('savednews').select("*").execute()
        return {"saved_articles": data.data}
    except Exception as e:
        return {"error": str(e)}

