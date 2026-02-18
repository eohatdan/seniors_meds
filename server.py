import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import requests
import fitz  # PyMuPDF
import re

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
        gemini_model = genai.GenerativeModel("gemini-2.5-flash")
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
def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False


def _is_date(s: str) -> bool:
    # 07/29/2025 style dates
    return bool(re.match(r"\d{2}/\d{2}/\d{4}$", s))


def _is_flag(s: str) -> bool:
    return s in {"High", "Low", "HIGH", "LOW", "H", "L"}


def _looks_like_reference(s: str) -> bool:
    # Things like "70-99", ">59", "<5.7", "Not Estab."
    if "Not Estab" in s:
        return True
    if re.search(r"[<>]", s):
        return True
    if re.search(r"\d", s) and "-" in s:
        return True
    return False


def _looks_like_units(s: str) -> bool:
    # If it looks like a reference interval, then it's *not* units.
    if _looks_like_reference(s):
        return False
    # Single "%" (for % differentials) counts as units.
    if s == "%":
        return True
    # Units usually have letters or slashes, e.g. mg/dL, x10E3/uL, pg/mL
    if re.search(r"[A-Za-z]", s) or "/" in s or "^" in s:
        return True
    return False


def extract_lab_data_from_text(text: str):
    """
    Parse Labcorp-style lab report text into structured readings.

    Each test appears as a vertical stack of lines, e.g.:

        WBC 01
        5.8
        5.8
        07/29/2025
        x10E3/uL
        3.4-10.8

    With optional flag:

        Glucose 01
        107
        High
        100
        07/29/2025
        mg/dL
        70-99

    Or without units (e.g. BUN/Creatinine Ratio):

        BUN/Creatinine Ratio
        15
        19
        07/29/2025
        10-24
    """

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    readings = []

    current_panel = None
    in_table = False
    i = 0

    while i < len(lines):
        ln = lines[i].strip()

        # ── Panel detection ────────────────────────────────────────
        if ln.startswith("CBC With Differential/Platelet"):
            current_panel = "CBC With Differential/Platelet"
            in_table = False
            i += 1
            continue

        if ln.startswith("Comp. Metabolic Panel (14)"):
            current_panel = "Comp. Metabolic Panel (14)"
            in_table = False
            i += 1
            continue

        if ln == "Lipid Panel":
            current_panel = "Lipid Panel"
            in_table = False
            i += 1
            continue

        if ln.startswith("B-Type Natriuretic Peptide"):
            current_panel = "B-Type Natriuretic Peptide"
            in_table = False
            i += 1
            continue

        # ── Table header row ──────────────────────────────────────
        if ln == "Test":
            if (
                i + 4 < len(lines)
                and "Current Result and Flag" in lines[i + 1]
                and "Previous Result and Date" in lines[i + 2]
                and lines[i + 3].strip() == "Units"
                and lines[i + 4].strip() == "Reference Interval"
            ):
                in_table = True
                i += 5
                continue

        # If we are not inside a known table, move on
        if not in_table or current_panel is None:
            i += 1
            continue

        # ── End-of-table / footer markers ─────────────────────────
        if (
            ln.startswith("Date Created and Stored")
            or ln.startswith("This document contains")
            or ln.startswith("Historical Results")
            or ln.startswith("Icon Legend")
            or ln.startswith("Performing Labs")
        ):
            in_table = False
            i += 1
            continue

        # ── Treat this line as a possible test name ───────────────
        name = ln.replace("\xa0", " ").strip()

        # Next line must be the current numeric result
        if i + 1 >= len(lines) or not _is_number(lines[i + 1].strip()):
            i += 1
            continue

        current_str = lines[i + 1].strip()
        j = i + 2

        flag = None
        previous = None
        previous_date = None
        units = None
        reference = None

        # Optional flag (High/Low/H/L)
        if j < len(lines) and _is_flag(lines[j].strip()):
            flag = lines[j].strip()
            j += 1

        # Previous numeric result
        if j < len(lines) and _is_number(lines[j].strip()):
            previous = lines[j].strip()
            j += 1

        # Previous result date
        if j < len(lines) and _is_date(lines[j].strip()):
            previous_date = lines[j].strip()
            j += 1

        # Optional units and reference
        if j < len(lines):
            cand = lines[j].strip()
            if _looks_like_units(cand):
                units = cand
                j += 1
                if j < len(lines):
                    ref_cand = lines[j].strip()
                    if _looks_like_reference(ref_cand) or not _looks_like_units(ref_cand):
                        reference = ref_cand
                        j += 1
            elif _looks_like_reference(cand):
                reference = cand
                j += 1

        # Convert current value to float
        try:
            value = float(current_str)
        except Exception:
            value = None

        # Convert previous if present
        prev_value = None
        if previous is not None and _is_number(previous):
            prev_value = float(previous)

        readings.append(
            {
                "panel": current_panel,
                "test_name": name,
                "value": value,
                "units": units,
                "reference": reference,
                "flags": flag,
                "previous": prev_value,
                "previous_date": previous_date,
            }
        )

        # Move to the next unread line
        i = j

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
