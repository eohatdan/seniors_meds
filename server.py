from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import openai
import jwt
import os

# Flask app setup
app = Flask(__name__)
CORS(app, origins=["https://eohatdan.github.io"], supports_credentials=True)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI setup
openai.api_key = os.getenv("OPENAI_API_KEY")
print("[DEBUG] Loaded OpenAI API Key:", "SET" if openai.api_key else "NOT SET")

# JWT decoding helper
def verify_token_and_get_user_id(auth_header):
    try:
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except Exception as e:
        print("JWT verification error:", e)
        return None

@app.route("/")
def home():
    return "SMA Server is running."

@app.route("/get-medications", methods=["POST"])
def get_medications():
    auth_header = request.headers.get("Authorization", "")
    user_id = verify_token_and_get_user_id(auth_header)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        result = supabase.table("medicationslist").select("*").eq("user_id", user_id).execute()
        return jsonify(result.data)
    except Exception as e:
        print("Medications query error:", e)
        return jsonify({"error": "Database query failed"}), 500

@app.route("/get-health-records", methods=["POST"])
def get_health_records():
    auth_header = request.headers.get("Authorization", "")
    user_id = verify_token_and_get_user_id(auth_header)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        result = supabase.table("healthRecords").select("*").eq("user_id", user_id).execute()
        return jsonify(result.data)
    except Exception as e:
        print("Health records query error:", e)
        return jsonify({"error": "Database query failed"}), 500

@app.route("/ask-openai", methods=["POST"])
def ask_openai():
    try:
        data = request.get_json()
        prompt = data.get("prompt")
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        print("[DEBUG] OpenAI Prompt Received:", prompt[:300])

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Temporarily use gpt-3.5-turbo for testing
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        return jsonify({"answer": answer})
    except Exception as e:
        print("OpenAI API error:", e)
        return jsonify({"error": "OpenAI request failed"}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
