from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)

# Setup OpenAI client (openai-python 1.0+)
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NEW"),
    base_url="https://api.openai.com/v1"
)

def compose_refined_prompt(user_question, medications):
    """
    Create a richer, conversational, context-specific refined prompt.
    """
    if not medications:
        return user_question  # fallback: raw question if no meds available

    med_list_text = "\n".join(
        f"- {med['name']} {med['dosage']} at {', '.join(med['times'])}"
        for med in medications
    )

    refined_prompt = f"""
You are a careful and friendly medical assistant helping a patient.

The patient is currently taking the following medications:
{med_list_text}

The patient asks: "{user_question}"

Please consider the patient's current medications when answering. 
Be specific if there are known risks, drug interactions, or recommendations. 
Write your response in a natural, conversational tone that is easy for a non-medical person to understand.
If appropriate, advise the patient to consult their healthcare provider.
""".strip()

    return refined_prompt

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()

        user_question = data.get('user_question')
        medications = data.get('medications', [])

        print("Received user_question:", user_question)  # Debug
        print("Received medications:", medications)      # Debug

        refined_prompt = compose_refined_prompt(user_question, medications)
        print("Refined Prompt Sent to OpenAI:", refined_prompt)  # Debug

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
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent (refined prompting with conversational tuning) is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
