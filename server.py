from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)  # <--- ADD THIS LINE to enable CORS

# Load OpenAI API key securely
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()
        messages = data.get('messages')

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        # Make OpenAI call
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=messages,
            temperature=0.7
        )
        return jsonify(response['choices'][0]['message']['content'])

    except Exception as e:
        # 🔥 Print full error to Railway logs
        print("Error occurred:", str(e))

        # Return the actual error message to the frontend temporarily
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent backend is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
