from flask import Flask, request, jsonify
from supabase import create_client
import os
import jwt

# Flask setup
app = Flask(__name__)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # Use service role if doing server-side admin ops
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # Found in Supabase dashboard

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Verify the JWT and extract user_id
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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
