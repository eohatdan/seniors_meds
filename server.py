from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import fitz  # PyMuPDF
from supabase import create_client, Client
import os

# Initialize app and CORS
app = Flask(__name__)
CORS(app)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI setup
openai.api_key = os.getenv("OPENAI_API_KEY")

# ========== AI Query Endpoint ==========

@app.route("/ask-openai", methods=["POST"])
def ask_openai():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    patient_id = data.get("patient_id")
    user_prompt = data.get("prompt")

    if not patient_id or not user_prompt:
        return jsonify({"error": "Missing patient_id or prompt"}), 400

    try:
        # Fetch patient data
        meds = supabase.table("medicationslist").select("*").eq("patient_id", patient_id).execute().data
        health = supabase.table("healthRecords").select("*").eq("patient_id", patient_id).execute().data
        surgeries = supabase.table("surgeryHistory").select("*").eq("patient_id", patient_id).execute().data
        lab_result = supabase.table("lab_reports").select("*").eq("patient_id", patient_id).order("date", desc=True).limit(1).execute().data

        # Build enhanced prompt
        enhanced_prompt = "Patient background:\n"

        if meds:
            enhanced_prompt += "\nMedications:\n"
            for med in meds:
                enhanced_prompt += f"- {med.get('medication', '')} ({med.get('dosage', '')}, {med.get('times', '')}x/day)\n"

        if health:
            hr = health[0]
            enhanced_prompt += "\nHealth Records:\n"
            enhanced_prompt += f"- Conditions: {hr.get('conditions', '')}\n"
            enhanced_prompt += f"- Allergies: {hr.get('allergies', '')}\n"
            enhanced_prompt += f"- Notes: {hr.get('notes', '')}\n"

        if surgeries:
            enhanced_prompt += "\nSurgical History:\n"
            for s in surgeries:
                enhanced_prompt += (
                    f"- {s.get('surgery_name', '')} on {s.get('surgery_date', '')} at "
                    f"{s.get('surgery_hospital', 'Unknown Hospital')} (Surgeon: {s.get('surgeon', 'Unknown')})\n"
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

        enhanced_prompt += f"\n\nUser question: {user_prompt}"
        print("Enhanced prompt: ",enhanced_prompt);
        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful health assistant reviewing patient records."},
                    {"role": "user", "content": enhanced_prompt}
                ]
            )
            reply = response.choices[0].message.content
            return jsonify({"response": reply})
        except Exception as e:
            return jsonify({"error": f"OpenAI failure: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== PDF Extraction Endpoint ==========

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
            except:
                continue
    return readings

def is_float(value):
    try:
        float(value)
        return True
    except:
        return False

# ========== Reset Password Endpoint ==========
@app.route("/admin-reset-password", methods=["POST"])
def admin_reset_password():
    data = request.get_json()
    print("Incoming reset payload:", data)

    if not data:
        return jsonify({"error": "No JSON received"}), 400

    email = data.get("email")
    new_password = data.get("new_password")

    if not email or not new_password:
        return jsonify({"error": "Missing email or new_password"}), 400

    try:
        # Step 1: Look up user by email
        user_result = supabase.auth.admin.list_users(email=email)
        user_list = user_result.get("users", []) if isinstance(user_result, dict) else []
        if not user_list:
            return jsonify({"error": "User not found"}), 404

        user_id = user_list[0]["id"]

        # Step 2: Reset password
        supabase_url = os.getenv("SUPABASE_URL")
        service_key = os.getenv("SUPABASE_SERVICE_KEY")

        import requests
        response = requests.post(
            f"{supabase_url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json"
            },
            json={"password": new_password}
        )

        if response.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({"error": response.json()}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ========== Render Entry Point ==========
  
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
