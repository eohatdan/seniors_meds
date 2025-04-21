from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Setup OpenAI client properly
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NEW"),
    base_url="https://api.openai.com/v1"
)

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()
        messages = data.get('messages')

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        return jsonify({"reply": response.choices[0].message.content})

    except Exception as e:
        print("Error occurred:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent backend is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
