from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os

app = Flask(__name__)
CORS(app)

# Set up OpenAI client (new 1.0+ style)
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    try:
        data = request.get_json()
        messages = data.get('messages')

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        # New 1.0+ syntax for chat completion
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        return jsonify(response.choices[0].message.content)

    except Exception as e:
        print("Error occurred:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent backend is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
