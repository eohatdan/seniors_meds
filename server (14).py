
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import os

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

@app.route("/")
def index():
    return "Server is running"

@app.route("/admin-reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    new_password = data.get("newPassword")

    if not email or not new_password:
        return jsonify({"error": "Email and new password required"}), 400

    try:
        user = client.auth.admin.get_user_by_email(email)
        if not user or not user.user:
            return jsonify({"error": f"User not found: {email}"}), 404

        user_id = user.user.id
        response = client.auth.admin.update_user_by_id(user_id, {
            "password": new_password
        })

        if response and response.user:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Password update failed"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
