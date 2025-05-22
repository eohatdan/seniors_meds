from flask import Flask, request, jsonify
from supabase import create_client
import os
import jwt
import openai
from flask_cors import CORS

# Flask setup
from flask_cors import CORS

CORS(app, origins=["https://eohatdan.github.io"], supports_credentials=True)


# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI setup
openai.api_key = os.getenv("OPENAI_API_KEY")

# JWT decoding
def verify_token_and_get_user_id(auth_header):
    try:
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")  # user_id (UUID)
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
        result = supabase.table("medicationsList").select("*").eq("user_id", user_id).execute()
        return jsonify(result.data)
    except Exception as e:
        print("Query error:", e)
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
        print("Query error:", e)
        return jsonify({"error": "Database query failed"}), 500

@app.route("/ask", methods=["POST"])
def ask_openai():
    data = request.get_json()
    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400

    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",  # or "gpt-3.5-turbo"
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        answer = completion.choices[0].message.content.strip()
        return jsonify({"answer": answer})
    except Exception as e:
        print("OpenAI API error:", e)
        return jsonify({"error": "OpenAI API request failed"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
