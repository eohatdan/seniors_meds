import os
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- LLMs ---
import openai  # using 0.28.x API for stability (chat.completions)
try:
    import google.generativeai as genai  # Gemini (optional)
except Exception:
    genai = None

# --- PDF parsing ---
import fitz  # PyMuPDF

# --- Supabase ---
from supabase import create_client  # requires supabase>=2.x

app = Flask(__name__)
CORS(app, supports_credentials=True)

# ──────────────────────────────────────────────────────────────────────────────
# Environment / Clients
# ──────────────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("WARNING: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

# Supabase client (named `client` per your preference)
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# OpenAI (0.28.x style)
openai.api_key = OPENAI_API_KEY

# Gemini (optional)
gemini_model = None
if GEMINI_API_KEY and genai is not None:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        print("Gemini init failed:", e)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def is_float(x):
    try:
        float(x)
        return True
    except Exception:
        return False


def extract_lab_data_from_text(text):
    """
    Very loose parser that tries to split lines like:
    'Sodium 140 mmol/L 135-145' or 'Glucose 98 mg/dL'
    into { test, result, units, ref_range, flag }
    """
    lines = text.splitlines()
    readings = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2:
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
                        remaining = parts[i + 1 :]
                        # optional flag like High/Low
                        if remaining and remaining[0] in ("High", "Low"):
                            flag = remaining[0]
                            units = remaining[1] if len(remaining) > 1 else ""
                            ref_range = " ".join(remaining[2:]) if len(remaining) > 2 else ""
                        else:
                            units = remaining[0] if len(remaining) > 0 else ""
                            ref_range = " ".join(remaining[1:]) if len(remaining) > 1 else ""
                        break

                if result:
                    readings.append(
                        {
                            "test": " ".join(name_parts),
                            "result": result,
                            "units": units,
                            "ref_range": ref_range,
                            "flag": flag,
                        }
                    )
            except Exception:
                continue
    return readings


# ──────────────────────────────────────────────────────────────────────────────
# AI endpoint
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/ask-openai", methods=["POST"])
def ask_openai():
    data = request.get_json() or {}
    patient_id = data.get("patient_id")
    user_prompt = data.get("prompt")
    llm_choice = data.get("llm_choice", "openai")

    if not patient_id or not user_prompt:
        return jsonify({"error": "Missing patient_id or prompt"}), 400

    try:
        meds = client.table("medicationslist").select("*").eq("patient_id", patient_id).execute().data
        health = client.table("healthRecords").select("*").eq("patient_id", patient_id).execute().data
        surgeries = client.table("surgeryHistory").select("*").eq("patient_id", patient_id).execute().data
        lab_result = (
            client.table("lab_reports")
            .select("*")
            .eq("patient_id", patient_id)
            .order("date", desc=True)
            .limit(1)
            .execute()
            .data
        )
        vital_signs = (
            client.table("vital_signs")
            .select("*")
            .eq("patient_id", patient_id)
            .order("recorded_at", desc=True)
            .limit(5)
            .execute()
            .data
        )

        enhanced = ["Patient background:"]

        if meds:
            enhanced.append("\nMedications:")
            for m in meds:
                enhanced.append(f"- {m.get('medication','')} ({m.get('dosage','')}, {m.get('times','')}x/day)")

        if health:
            hr = health[0]
            enhanced.append("\nHealth Records:")
            enhanced.append(f"- Conditions: {hr.get('condition','')}")
            enhanced.append(f"- Allergies: {hr.get('allergies','')}")
            if hr.get("notes"):
                enhanced.append(f"- Notes: {hr.get('notes')}")

        if surgeries:
            enhanced.append("\nSurgical History:")
            for s in surgeries:
                enhanced.append(
                    f"- {s.get('surgery_name','')} on {s.get('surgery_date','')} "
                    f"at {s.get('hospital','Unknown Hospital')} (Surgeon: {s.get('surgeon','Unknown')})"
                )

        if lab_result:
            readings = lab_result[0].get("readings", [])
            if isinstance(readings, list) and readings:
                enhanced.append("\nRecent Lab Readings:")
                for r in readings:
                    line = f"- {r.get('test','')}: {r.get('result','')} {r.get('units','')}"
                    if r.get("flag"):
                        line += f" ({r['flag']})"
                    if r.get("ref_range"):
                        line += f" [Ref: {r['ref_range']}]"
                    enhanced.append(line)

        if vital_signs:
            enhanced.append("\nRecent Vital Signs:")
            for vs in vital_signs:
                recorded_at = vs.get("recorded_at", "")
                line = f"- When: {recorded_at}"
                if vs.get("average_weight") is not None:
                    line += f", Weight: {vs['average_weight']} lbs"
                if vs.get("average_glucose") is not None:
                    line += f", Glucose: {vs['average_glucose']} mg/dL"
                if vs.get("average_systolic") is not None and vs.get("average_diastolic") is not None:
                    line += f", BP: {vs['average_systolic']}/{vs['average_diastolic']} mmHg"
                if vs.get("average_oxygen") is not None:
                    line += f", O2 Sat: {vs['average_oxygen']}%"
                if vs.get("heart_rate") is not None:
                    line += f", HR: {vs['heart_rate']} bpm"
                if vs.get("notes"):
                    line += f" (Notes: {vs['notes']})"
                enhanced.append(line)

        enhanced.append("\n\nUser question: " + user_prompt)
        enhanced_prompt = "\n".join(enhanced)

        if llm_choice == "openai":
            resp = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful health assistant reviewing patient records."},
                    {"role": "user", "content": enhanced_prompt},
                ],
            )
            reply = resp.choices[0].message["content"]
        elif llm_choice == "gemini":
            if not gemini_model:
                return jsonify({"error": "Gemini not configured"}), 500
            reply = gemini_model.generate_content(enhanced_prompt).text
        else:
            return jsonify({"error": "Invalid LLM choice"}), 400

        return jsonify({"response": reply})
    except Exception as e:
        print("Error in /ask-openai:", e)
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Lab readings extraction
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/extract-readings", methods=["POST"])
def extract_readings():
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf_file = request.files["pdf"]
    try:
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        readings = extract_lab_data_from_text(text)
        return jsonify({"readings": readings})
    except Exception as e:
        print("Error in /extract-readings:", e)
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Admin: reset password
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/admin-reset-password", methods=["POST"])
def admin_reset_password():
    try:
        data = request.get_json(force=True)
        email = data.get("email")
        new_password = data.get("new_password")
        if not email or not new_password:
            return jsonify({"error": "Missing email or new_password"}), 400

        user_list_response = client.auth.admin.list_users()
        users = user_list_response.get("users", []) if isinstance(user_list_response, dict) else user_list_response

        target_user_id = None
        for u in users:
            if isinstance(u, dict) and u.get("email") == email:
                target_user_id = u.get("id")
                break

        if not target_user_id:
            return jsonify({"error": "User not found"}), 404

        client.auth.admin.update_user_by_id(target_user_id, {"password": new_password})
        return jsonify({"success": True})
    except Exception as e:
        print("Error in /admin-reset-password:", e)
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Vital signs
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/vital-signs", methods=["POST"])
def add_vital_signs():
    """
    JSON payload:
    {
      "patient_id": "...",
      "recorded_at": "YYYY-MM-DDTHH:MM",
      "average_weight": 150.2,
      "average_glucose": 95.0,
      "average_systolic": 120,
      "average_diastolic": 80,
      "average_oxygen": 98.5,
      "heart_rate": 72,
      "notes": "after breakfast"
    }
    """
    data = request.get_json() or {}
    patient_id = data.get("patient_id")
    recorded_at = data.get("recorded_at")

    if not patient_id or not recorded_at:
        return jsonify({"error": "Missing patient_id or recorded_at"}), 400

    payload = {
        "patient_id": patient_id,
        "recorded_at": recorded_at,  # Postgres accepts ISO-like strings
        "average_weight": data.get("average_weight"),
        "average_glucose": data.get("average_glucose"),
        "average_systolic": data.get("average_systolic"),
        "average_diastolic": data.get("average_diastolic"),
        "average_oxygen": data.get("average_oxygen"),
        "heart_rate": data.get("heart_rate"),
        "notes": data.get("notes"),
    }
    # Strip None values
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        res = client.table("vital_signs").insert(payload).execute()
        return jsonify({"success": True, "data": res.data}), 201
    except Exception as e:
        print("Error in /vital-signs POST:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/vital-signs/<patient_id>", methods=["GET"])
def get_vital_signs(patient_id):
    try:
        res = (
            client.table("vital_signs")
            .select("*")
            .eq("patient_id", patient_id)
            .order("recorded_at", desc=True)
            .execute()
        )
        return jsonify({"success": True, "data": res.data}), 200
    except Exception as e:
        print("Error in /vital-signs GET:", e)
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
