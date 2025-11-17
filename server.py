import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import fitz  # PyMuPDF

# Optional Gemini
try:
    import google.generativeai as genai
except Exception:
    genai = None

app = Flask(__name__)
CORS(app, supports_credentials=True)

# ── Env ───────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing")

openai.api_key = OPENAI_API_KEY

gemini_model = None
if GEMINI_API_KEY and genai is not None:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        print("Gemini init failed:", e)

# ── Supabase REST helpers ─────────────────────────────────────────────
REST_URL = f"{SUPABASE_URL}/rest/v1"
REST_HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def sb_select(table, eq=None, order=None, limit=None):
    """
    eq: dict of column -> value
    order: tuple (col, desc_bool)
    """
    params = {}
    if eq:
        for k, v in eq.items():
            params[f"{k}"] = f"eq.{v}"
    if order:
        col, desc = order
        params["order"] = f"{col}.{'desc' if desc else 'asc'}"
    if limit:
        params["limit"] = str(limit)
    r = requests.get(f"{REST_URL}/{table}", headers=REST_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def sb_insert(table, payload):
    r = requests.post(f"{REST_URL}/{table}", headers=REST_HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

# ── Utilities ────────────────────────────────────────────────────────
def is_float(x):
    try:
        float(x)
        return True
    except Exception:
        return False

import re

def extract_lab_data_from_text(text: str):
    """
    Parse common lab report lines into structured readings.

    Returns a list of dicts like:
    {
      "test_name": "Glucose",
      "value": 102.0,
      "units": "mg/dL",
      "reference": "65-99",
      "flags": "H"  # optional
    }
    """

    readings = []

    # Normalize whitespace a bit
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Example row formats this is trying to capture:
    #
    #   Glucose               102    mg/dL       65-99
    #   Hemoglobin A1c        6.8    %          <5.7
    #   Sodium                140    mmol/L     135-145
    #
    # Sometimes with flags:
    #   Glucose               112 H  mg/dL      65-99
    #
    # We allow:
    #   test_name  value [flag] units [reference]
    #
    row_pattern = re.compile(
        r"""
        ^\s*
        (?P<name>[A-Za-z0-9 /(),.%+-]+?)   # test name (fairly loose)
        \s+
        (?P<value>-?\d+(?:\.\d+)?)         # numeric value
        (?:\s+(?P<flag>[A-Z*]+))?          # optional flag(s): H, L, etc.
        \s+
        (?P<units>[A-Za-z/%µ\^0-9]+)?      # optional units (mg/dL, mmol/L, %, etc.)
        (?:\s+(?P<ref>[0-9A-Za-z .\-–<>/]+))?   # optional reference range / note
        \s*$
        """,
        re.VERBOSE
    )

    for ln in lines:
        m = row_pattern.match(ln)
        if not m:
            # If you want to see what isn't matching while tuning, uncomment:
            # print("NO MATCH:", repr(ln))
            continue

        name = (m.group("name") or "").strip()
        value_str = m.group("value")
        flag = (m.group("flag") or "").strip()
        units = (m.group("units") or "").strip()
        ref = (m.group("ref") or "").strip()

        # Convert numeric value if possible
        try:
            value_num = float(value_str)
        except (TypeError, ValueError):
            value_num = None

        readings.append({
            "test_name": name,
            "value": value_num,
            "units": units or None,
            "reference": ref or None,
            "flags": flag or None,
        })

    return readings


# ── AI endpoint ──────────────────────────────────────────────────────
@app.route("/ask-openai", methods=["POST"])
def ask_openai_route():
    data = request.get_json() or {}
    patient_id = data.get("patient_id")
    user_prompt = data.get("prompt")
    llm_choice = data.get("llm_choice", "openai")

    if not patient_id or not user_prompt:
        return jsonify({"error": "Missing patient_id or prompt"}), 400

    try:
        meds = sb_select("medicationslist", eq={"patient_id": patient_id})
        health = sb_select("healthRecords", eq={"patient_id": patient_id})
        surgeries = sb_select("surgeryHistory", eq={"patient_id": patient_id})
        lab_result = sb_select("lab_reports", eq={"patient_id": patient_id}, order=("date", True), limit=1)
        vital_signs = sb_select("vital_signs", eq={"patient_id": patient_id}, order=("recorded_at", True), limit=5)

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
                line = f"- When: {vs.get('recorded_at','')}"
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
    except requests.HTTPError as e:
        return jsonify({"error": f"Supabase REST error: {e.response.text}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Lab readings extraction ──────────────────────────────────────────
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
        return jsonify({"error": str(e)}), 500

# ── Vital signs ─────────────────────────────────────────────────────
@app.route("/vital-signs", methods=["POST"])
def add_vital_signs():
    data = request.get_json() or {}
    patient_id = data.get("patient_id")
    recorded_at = data.get("recorded_at")
    if not patient_id or not recorded_at:
        return jsonify({"error": "Missing patient_id or recorded_at"}), 400

    payload = {
        "patient_id": patient_id,
        "recorded_at": recorded_at,  # ISO-like string accepted by Postgres
        "average_weight": data.get("average_weight"),
        "average_glucose": data.get("average_glucose"),
        "average_systolic": data.get("average_systolic"),
        "average_diastolic": data.get("average_diastolic"),
        "average_oxygen": data.get("average_oxygen"),
        "heart_rate": data.get("heart_rate"),
        "notes": data.get("notes"),
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        inserted = sb_insert("vital_signs", payload)
        return jsonify({"success": True, "data": inserted}), 201
    except requests.HTTPError as e:
        return jsonify({"error": f"Supabase REST insert error: {e.response.text}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/vital-signs/<patient_id>", methods=["GET"])
def get_vital_signs(patient_id):
    try:
        rows = sb_select("vital_signs", eq={"patient_id": patient_id}, order=("recorded_at", True))
        return jsonify({"success": True, "data": rows}), 200
    except requests.HTTPError as e:
        return jsonify({"error": f"Supabase REST select error: {e.response.text}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Admin reset (left as-is; SDK-free approach would need GoTrue REST/JWT) ───
# If you use this route, we should port it to GoTrue Admin REST. For now, keep disabled or remove.
@app.route("/admin-reset-password", methods=["POST"])
def admin_reset_password():
    return jsonify({"error": "Admin reset not implemented without SDK"}), 501

# ── Entrypoint ───────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
