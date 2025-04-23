from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import sys

app = Flask(__name__)
CORS(app)

# Setup OpenAI client (openai-python 1.0+)
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NEW"),
    base_url="https://api.openai.com/v1"
)

import sys

def compose_refined_prompt(user_question, medications):
    """
    Create a context-rich, refined prompt that requires OpenAI to review medications and explain reasoning.
    """
    if not medications:
        return user_question  # fallback if no meds available

    med_list_text = "\n".join(
        f"- {med['medication']} {med['dosage']} at {', '.join(med['times'])}"
        for med in medications
    )

    refined_prompt = f"""
You are a careful and helpful medical assistant.

The patient is currently taking the following medications:
{med_list_text}

The patient has asked the following question:
"{user_question}"

Please do the following carefully:
- Explicitly evaluate the listed medications for any possible interactions or contraindications related to the patient's question.
- If there is a concern, explain clearly why (e.g., "because it may increase bleeding risk when combined with X...").
- If there is no concern, state that clearly too ("because there are no known interactions between these medications and ibuprofen").
- Always provide simple, patient-friendly language that a non-medical person can easily understand.
- End by advising whether it is safe or if they should consult their doctor before taking action.
""".strip()

    return refined_prompt


@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()

        user_question = data.get('user_question')
        medications = data.get('medications', [])

        print("Received user_question:", user_question)  # Debug
        sys.stdout.flush()          
        print("Received medications:", medications)      # Debug
        sys.stdout.flush()           

        refined_prompt = compose_refined_prompt(user_question, medications)
        print("Refined Prompt Sent to OpenAI:", refined_prompt)  # Debug
        sys.stdout.flush()              

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a careful and helpful medical assistant."},
                {"role": "user", "content": refined_prompt}
            ],
            temperature=0.85  # 🛠️ Increased for slight stylistic variability
        )

        return jsonify({"reply": response.choices[0].message.content})

    except Exception as e:
        print("Error occurred:", str(e))
        sys.stdout.flush()        
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent (refined prompting with conversational tuning) is running."

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
        threaded=True
    )
