from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import sys

app = Flask(__name__)
CORS(app)

client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NEW"),
    base_url="https://api.openai.com/v1"
)

def compose_refined_prompt(user_question, medications, health_records):
    meds_text = "\n".join(f"- {m['medication']} {m['dosage']}" for m in medications)

    conditions = health_records.get("conditions", [])
    allergies = health_records.get("allergies", [])
    notes = health_records.get("notes", "")

    conditions_text = "\n".join(f"- {c}" for c in conditions)
    allergies_text = "\n".join(f"- {a}" for a in allergies)

    return f"""
You are a careful and helpful medical assistant.

Please use the following information to answer the user's question. Be sure to state clearly that you reviewed both their medications and health records before responding.

Current Medications:
{meds_text or 'None'}

Medical Conditions:
{conditions_text or 'None'}

Allergies:
{allergies_text or 'None'}

Additional Notes:
{notes or 'None'}

The user asked:
"{user_question}"

Please consider all the above data and answer safely, clearly, and in patient-friendly language.
""".strip()

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()
        user_question = data.get('user_question')
        medications = data.get('medications', [])
        health_records = data.get('health_records', {})

        print("Received question:", user_question)
        print("Meds:", medications)
        print("Health records:", health_records)
        sys.stdout.flush()

        refined_prompt = compose_refined_prompt(user_question, medications, health_records)

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a careful and helpful medical assistant."},
                {"role": "user", "content": refined_prompt}
            ],
            temperature=0.85
        )

        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        print("Error:", e)
        sys.stdout.flush()
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent with Health Records is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True, threaded=True)
