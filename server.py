import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()

        user_question = data.get("user_question", "")
        medications = data.get("medications", [])
        healthRecords = data.get("healthRecords", [])
        surgeryHistory = data.get("surgeryHistory", [])

        # Compose refined prompt
        refined_prompt = f"""
The user asked: {user_question}

Consider their current medications:
{json.dumps(medications, indent=2)}

Consider their health records:
{json.dumps(healthRecords, indent=2)}

Consider their surgery history:
{json.dumps(surgeryHistory, indent=2)}

Using this information, provide a helpful, safe, and medically-informed answer. 
Clearly state that medications, health records, and surgery history were considered.
"""

        # Send to OpenAI
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": refined_prompt}],
            max_tokens=800,
            temperature=0.5,
        )

        ai_response = response.choices[0].message.content.strip()

        return jsonify({"response": ai_response})

    except Exception as e:
        print(f"Error occurred: {e}")
        return jsonify({"response": "❗ Error contacting OpenAI."}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
