import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import fitz  # PyMuPDF
from supabase import create_client
import google.generativeai as genai # Import Gemini API library

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Load API keys from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Load Gemini API Key

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY

# Initialize Supabase client
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Initialize Gemini client if API key is available
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.0-flash') # Use gemini-2.0-flash as specified
else:
    gemini_model = None # Gemini will not be available if key is missing
    print("Warning: GEMINI_API_KEY not found. Gemini API will not be available.")


@app.route("/ask-openai", methods=["POST"])
def ask_openai():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    patient_id = data.get("patient_id")
    user_prompt = data.get("prompt")
    llm_choice = data.get("llm_choice", "openai") # Get LLM choice, default to openai

    if not patient_id or not user_prompt:
        return jsonify({"error": "Missing patient_id or prompt"}), 400

    try:
        # --- Data Retrieval (common for both LLMs) ---
        meds = client.table("medicationslist").select("*").eq("patient_id", patient_id).execute().data
        health = client.table("healthRecords").select("*").eq("patient_id", patient_id).execute().data
        surgeries = client.table("surgeryHistory").select("*").eq("patient_id", patient_id).execute().data
        lab_result = client.table("lab_reports").select("*").eq("patient_id", patient_id).order("date", desc=True).limit(1).execute().data
        
        # Retrieve vital signs data
        vital_signs = client.table("vital_signs").select("*").eq("patient_id", patient_id).order("recorded_at", desc=True).limit(5).execute().data # Get last 5 vital sign entries

        enhanced_prompt = "Patient background:\n"

        if meds:
            enhanced_prompt += "\nMedications:\n"
            for med in meds:
                enhanced_prompt += f"- {med.get('medication', '')} ({med.get('dosage', '')}, {med.get('times', '')}x/day)\n"

        if health:
            if health:
                hr = health[0]
                enhanced_prompt += "\nHealth Records:\n"
                enhanced_prompt += f"- Conditions: {hr.get('condition', '')}\n"
                enhanced_prompt += f"- Allergies: {hr.get('allergies', '')}\n"
                enhanced_prompt += f"- Notes: {hr.get('notes', '')}\n"
                enhanced_prompt += f"- Date Condition Began: {hr.get('start_date', '')}\n"

        if surgeries:
            enhanced_prompt += "\nSurgical History:\n"
            for s in surgeries:
                enhanced_prompt += (
                    f"- {s.get('surgery_name', '')} on {s.get('surgery_date', '')} at "
                    f"{s.get('hospital', 'Unknown Hospital')} (Surgeon: {s.get('surgeon', 'Unknown')})\n"
                )

        if lab_result:
            readings = lab_result[0].get('readings', [])
            if isinstance(readings, list) and readings:
                enhanced_prompt += "\nRecent Lab Readings:\n"
                for r in readings:
                    line = f"- {r.get('test', '')}: {r.get('result', '')} {r.get('units', '')}"
                    if r.get('flag'):
                        line += f" ({r['flag']})"
                    if r.get('ref_range'):
                        line += f" [Ref: {r['ref_range']}]"
                    enhanced_prompt += line + "\n"
        
        if vital_signs:
            enhanced_prompt += "\nRecent Vital Signs:\n"
            for vs in vital_signs:
                enhanced_prompt += f"- Date: {vs.get('recorded_at', '').split('T')[0]}"
                if vs.get('average_weight') is not None:
                    enhanced_prompt += f", Weight: {vs.get('average_weight')} lbs"
                if vs.get('average_glucose') is not None:
                    enhanced_prompt += f", Glucose: {vs.get('average_glucose')} mg/dL"
                if vs.get('average_systolic') is not None and vs.get('average_diastolic') is not None:
                    enhanced_prompt += f", BP: {vs.get('average_systolic')}/{vs.get('average_diastolic')} mmHg"
                if vs.get('average_oxygen') is not None:
                    enhanced_prompt += f", O2 Sat: {vs.get('average_oxygen')}%"
                if vs.get('notes'):
                    enhanced_prompt += f" (Notes: {vs.get('notes')})"
                enhanced_prompt += "\n"

        enhanced_prompt += f"\n\nUser question: {user_prompt}"

        # --- LLM Selection and Call ---
        reply = ""
        if llm_choice == "openai":
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful health assistant reviewing patient records."},
                    {"role": "user", "content": enhanced_prompt}
                ]
            )
            reply = response.choices[0].message.content
        elif llm_choice == "gemini":
            if gemini_model:
                # Gemini API call
                gemini_response = gemini_model.generate_content(enhanced_prompt)
                reply = gemini_response.text
            else:
                return jsonify({"error": "Gemini API not configured. GEMINI_API_KEY might be missing."}), 500
        else:
            return jsonify({"error": "Invalid LLM choice provided."}), 400

        return jsonify({"response": reply})

    except Exception as e:
        print(f"Error in /ask-openai: {e}") # Log the error for debugging
        return jsonify({"error": str(e)}), 500

@app.route("/extract-readings", methods=["POST"])
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
        print(f"Error in /extract-readings: {e}") # Log the error
        return jsonify({'error': str(e)}), 500

def extract_lab_data_from_text(text):
    lines = text.splitlines()
    readings = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            try:
                name_parts = []
                result = None
                units = ""
                ref_range = ""
                flag = None

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
            except Exception as e: # Catch specific errors in parsing loop
                print(f"Error parsing line '{line}': {e}")
                continue
    return readings

def is_float(value):
    try:
        float(value)
        return True
    except:
        return False

@app.route("/admin-reset-password", methods=["POST"])
def admin_reset_password():
    try:
        data = request.get_json(force=True)
        print("Incoming reset payload:", data)

        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request format"}), 400

        email = data.get("email")
        new_password = data.get("new_password")

        if not email or not new_password:
            return jsonify({"error": "Missing email or new_password"}), 400

        user_list_response = client.auth.admin.list_users()
        users = user_list_response.get("users", []) if isinstance(user_list_response, dict) else user_list_response

        target_user_id = None
        for user in users:
            if isinstance(user, dict) and user.get("email") == email:
                target_user_id = user.get("id")
                break

        if not target_user_id:
            return jsonify({"error": "User not found"}), 404

        client.auth.admin.update_user_by_id(target_user_id, {
            "password": new_password
        })

        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Error in /admin-reset-password: {e}") # Log the error
        return jsonify({"error": str(e)}), 500

# --- New Vital Signs Endpoints ---

@app.route("/vital-signs", methods=["POST"])
def add_vital_signs():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    patient_id = data.get("patient_id")
    recorded_at = data.get("recorded_at") # Expecting ISO format date/time string
    
    # Extract vital sign values, allowing them to be optional
    average_weight = data.get("average_weight")
    average_glucose = data.get("average_glucose")
    average_systolic = data.get("average_systolic")
    average_diastolic = data.get("average_diastolic")
    average_oxygen = data.get("average_oxygen")
    notes = data.get("notes")

    if not patient_id or not recorded_at:
        return jsonify({"error": "Missing patient_id or recorded_at"}), 400

    try:
        # Prepare payload for Supabase insert
        payload = {
            "patient_id": patient_id,
            "recorded_at": recorded_at,
            "average_weight": average_weight,
            "average_glucose": average_glucose,
            "average_systolic": average_systolic,
            "average_diastolic": average_diastolic,
            "average_oxygen": average_oxygen,
            "notes": notes
        }
        
        # Filter out None values to avoid inserting nulls if not provided
        payload = {k: v for k, v in payload.items() if v is not None}

        response = client.table("vital_signs").insert(payload).execute()
        
        if response.data:
            return jsonify({"success": True, "data": response.data}), 201
        else:
            print(f"Supabase insert error for vital signs: {response.error}")
            return jsonify({"error": response.error.message}), 500

    except Exception as e:
        print(f"Error in /vital-signs POST: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/vital-signs/<patient_id>", methods=["GET"])
def get_vital_signs(patient_id):
    try:
        response = client.table("vital_signs").select("*").eq("patient_id", patient_id).order("recorded_at", desc=True).execute()
        
        if response.data:
            return jsonify({"success": True, "data": response.data}), 200
        else:
            print(f"Supabase select error for vital signs: {response.error}")
            return jsonify({"error": response.error.message}), 500

    except Exception as e:
        print(f"Error in /vital-signs GET: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
