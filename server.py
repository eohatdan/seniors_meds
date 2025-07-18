from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import fitz  # PyMuPDF
from supabase import create_client
import os

# === Setup ===
app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

openai.api_key = os.getenv("OPENAI_API_KEY")


# === AI Query Endpoint ===
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
        # Fetch records
        meds = client.table("medicationslist").select("*").eq("patient_id", patient_id).execute().data
        health = client.table("healthRecords").select("*").eq("patient_id", patient_id).execute().data
        surgeries = client.table("surgeryHistory").select("*").eq("patient_id", patient_id).execute().data
        lab_result = client.table("lab_reports").select("*").eq("patient_id", patient_id).order("date", desc=True).limit(1).execute().data

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
        print("Enhanced prompt:\n", enhanced_prompt)

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
        return jsonify({"error": f"AI query failed: {str(e)}"}), 500


# === PDF Lab Report Extraction Endpoint ===
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
                        remaining = parts[i + 1:]
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


# === Password Reset via UUID (preferred) ===
@app.route("/admin-reset-password-uuid", methods=["POST"])
def admin_reset_password_uuid():
    try:
        data = request.get_json()
        uuid = data.get("uuid")
        new_password = data.get("new_password")

        if not uuid or not new_password:
            return jsonify({"error": "UUID and new password required"}), 400

        result = client.auth.admin.update_user_by_id(uuid, {"password": new_password})

        if result.user:
            return jsonify({"message": "✅ Password reset successful"}), 200
        else:
            return jsonify({"error": "Update failed"}), 500

    except Exception as e:
        return jsonify({"error": f"Reset failed: {str(e)}"}), 500


# === Render Entry Point ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
