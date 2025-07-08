from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import openai
import jwt
import os
import traceback
import fitz  # PyMuPDF

app = Flask(__name__)
CORS(app)

# Flask app setup
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # allow all for dev, tighten later

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

        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        answer = response.choices[0].message.content.strip()
        return jsonify({"answer": answer})

    except Exception as e:
        print("OpenAI API error:", e)
        traceback.print_exc()
        return jsonify({"error": "OpenAI request failed"}), 500

@app.route('/extract-readings', methods=['POST'])
def extract_readings():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No PDF uploaded'}), 400

    pdf_file = request.files['pdf']
    try:
        doc = fitz.open(stream=pdf_file.read(), filetype='pdf')
        text = "\n".join(page.get_text() for page in doc)
        readings = extract_lab_data_from_text(text)
        return jsonify({'readings': readings})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def extract_lab_data_from_text(text):
    lines = text.splitlines()
    readings = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            try:
                # Find numeric result (could be position 1 or 2)
                name_parts = []
                units = ""
                ref_range = ""
                flag = None
                result = None

                for i, part in enumerate(parts):
                    if is_float(part):
                        result = part
                        name_parts = parts[:i]
                        remaining = parts[i+1:]
                        if remaining and remaining[0] in ["High", "Low"]:
                            flag = remaining[0]
                            units = remaining[1] if len(remaining) > 1 else ""
                            ref_range = " ".join(remaining[2:])
                        else:
                            units = remaining[0] if len(remaining) > 0 else ""
                            ref_range = " ".join(remaining[1:])
                        break

                if result:
                    readings.append({
                        "test": " ".join(name_parts),
                        "result": result,
                        "flag": flag,
                        "units": units,
                        "ref_range": ref_range
                    })
            except:
                continue
    return readings

def is_float(value):
    try:
        float(value)
        return True
    except:
        return False


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
