from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)

# Setup OpenAI client (using openai-python >= 1.0.0 style)
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NEW"),
    base_url="https://api.openai.com/v1"
)

def compose_refined_prompt(user_question, medications):
    """
    Create a context-rich, refined prompt using user's question and medication list.
    """
    if not medications:
        return user_question  # fallback: just the question if no meds available

    med_list_text = "\n".join(
        f"- {med['name']} {med['dosage']} at {', '.join(med['times'])}"
        for med in medications
    )

    refined_prompt = f"""
You are a careful and helpful medical assistant.

Here is the patient's current list of medications:
{med_list_text}

The patient asked: "{user_question}"

Considering the patient's medications, provide a clear and medically appropriate answer.
""".strip()

    return refined_prompt

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()

        user_question = data.get('user_question')
        medications = data.get('medications', [])

        print("Received user_question:", user_question)  # For debugging
        print("Received medications:", medications)      # For debugging

        refined_prompt = compose_refined_prompt(user_question, medications)

        print("Refined Prompt Sent to OpenAI:", refined_prompt)  # For debugging

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a careful and helpful medical assistant."},
                {"role": "user", "content": refined_prompt}
            ],
            temperature=0.7
        )

        # Return just the assistant's reply text
        return jsonify({"reply": response.choices[0].message.content})

    except Exception as e:
        print("Error occurred:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent (self-prompting with refined prompts) is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
