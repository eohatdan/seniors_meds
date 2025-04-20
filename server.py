from flask import Flask, request, jsonify
import openai
import os

app = Flask(__name__)

# Load OpenAI API key securely from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/ask-openai', methods=['POST'])
def ask_openai():
    data = request.get_json()
    messages = data.get('messages')

    if not messages:
        return jsonify({"error": "No messages provided"}), 400

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=messages,
            temperature=0.7
        )
        return jsonify(response['choices'][0]['message']['content'])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "SMA AI Meds Agent API is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
