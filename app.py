import os
import json
import base64
from flask import Flask, render_template, request, redirect, url_for, flash
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai # Import the Gemini API library

app = Flask(__name__)
# IMPORTANT: Change this to a strong, random key for session security!
# You can generate one with `import os; print(os.urandom(24).hex())` in Python
app.secret_key = '7de397806f37b08283c6bdd4936c94a23f4935946077a039'

# --- Firebase Initialization ---
# Ensure the Firebase app is initialized only once
if not firebase_admin._apps:
    # Try to get credentials from environment variable for deployment
    service_account_key_base64 = os.environ.get('SERVICE_ACCOUNT_KEY_BASE64')

    if service_account_key_base64:
        try:
            service_account_info = json.loads(base64.b64decode(service_account_key_base64))
            cred = credentials.Certificate(service_account_info)
        except (json.JSONDecodeError, base64.binascii.Error) as e:
            # Fallback for local development if environment variable is malformed
            print(f"Error decoding service account key from environment: {e}")
            cred = credentials.ApplicationDefault()
    else:
        # Fallback for local development using GOOGLE_APPLICATION_CREDENTIALS or default ADC
        cred = credentials.ApplicationDefault()

    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Gemini API Configuration ---
# IMPORTANT: For local development, load directly from os.environ.get with a fallback.
# For deployment, ensure the "GEMINI_API_KEY" environment variable is set in Cloud Run.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_ACTUAL_GEMINI_API_KEY_HERE")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro') # Using gemini-pro for text generation

# --- Flask Routes ---

@app.route('/')
def index():
    # Fetch all quotes/facts from Firestore, ordered by timestamp
    # Ensure a composite index is created in Firestore for this query if needed:
    # Collection: 'quotes', Fields: 'timestamp' (Descending), '__name__' (Descending)
    quotes_ref = db.collection('quotes').order_by('timestamp', direction=firestore.Query.DESCENDING)
    quotes = []
    try:
        # Stream documents and convert them to dictionaries
        for doc in quotes_ref.stream():
            quotes.append(doc.to_dict())
    except Exception as e:
        print(f"Error fetching quotes from Firestore: {e}")
        flash(f"Error loading wisdom: {e}", 'danger')

    return render_template('index.html', quotes=quotes)

@app.route('/submit_quote', methods=['POST'])
def submit_quote():
    quote_text = request.form['quote_text'].strip()
    source_text = request.form.get('source', '').strip() # Get source, default to empty string
    
    if not source_text: # If source is empty, set default value
        source_text = "User Submission"

    if quote_text:
        new_quote = {
            'text': quote_text,
            'source': source_text,
            'timestamp': firestore.SERVER_TIMESTAMP # Firestore automatically adds server timestamp
        }
        try:
            db.collection('quotes').add(new_quote)
            flash('Quote/Fact submitted successfully!', 'success')
        except Exception as e:
            print(f"Error adding user submitted quote: {e}")
            flash(f'Error submitting wisdom: {e}', 'danger')
    else:
        flash('Quote/Fact cannot be empty!', 'danger')
    return redirect(url_for('index'))

@app.route('/generate_quote', methods=['POST'])
def generate_quote():
    # Prompt the Gemini API for content
    prompt = "Generate a short, inspiring quote or an interesting, lesser-known fun fact. Do not provide a source. Just the quote/fact itself."
    try:
        response = model.generate_content(prompt)
        ai_generated_text = response.text.strip()
        
        if ai_generated_text:
            new_quote = {
                'text': ai_generated_text,
                'source': 'AI Generated (Gemini)',
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            db.collection('quotes').add(new_quote)
            flash('AI-generated content added!', 'success')
        else:
            flash('Could not generate content from AI. Please try again.', 'danger')
    except Exception as e:
        # Log the full error for debugging in Cloud Logging
        print(f"Error generating AI content: {e}")
        flash(f'Error generating content: {e}', 'danger')
    return redirect(url_for('index'))

# --- Cloud Run specific host/port configuration ---
if __name__ == '__main__':
    # Get the port from the environment variable, default to 8080 if not set (Cloud Run sets it)
    port = int(os.environ.get("PORT", 8080))
    # Run the app, listening on all public IPs (0.0.0.0) and the specified port
    # Set debug=False for production for security and performance
    app.run(host="0.0.0.0", port=port, debug=False)

