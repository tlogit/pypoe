from flask import Flask, request, render_template, redirect, url_for
import os
import fitz  # PyMuPDF
from werkzeug.utils import secure_filename
import requests

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def analyze_pdf_with_llama3(pdf_path):
    results = []
    signature_issues = []

    doc = fitz.open(pdf_path)
    num_pages = len(doc)

    # Check for raw signature tag
    with open(pdf_path, "rb") as f:
        raw_data = f.read()
        signature_tag_found = b"<</Subtype/page/Type/FillSignData>>" in raw_data

    for i in range(num_pages):
        page = doc.load_page(i)
        text = page.get_text()

        prompt = f"""
You are a POE (Portfolio of Evidence) evaluator.

Instructions:
- Look for unanswered questions (e.g., "Question No. 1") or activities (e.g., "Activity No. 2.1") that have no student input.
- Unanswered sections may contain text like: "Click or tap here to enter text", "Enter answer here", or be blank under the heading.
- Also look for missing or incomplete sections titled: Reflection, Logbook, CCFO, or Declaration.
- Mention if a signature is referenced but not filled.

Your task:
From the text below, output a structured summary of:
1. Which questions or activities are unanswered.
2. Whether Reflection, Logbook, CCFO, or Declaration are missing.
3. If nothing is missing, respond with "All fields appear to be completed."

TEXT START
{text}
TEXT END
"""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3:8b-q4_K_M", "prompt": prompt, "stream": False},
                timeout=60
            )
            analysis = response.json().get("response", "").strip()
        except Exception as e:
            analysis = f"Error analyzing page {i+1}: {str(e)}"

        # Add signature check
        if "signature" in text.lower() and not signature_tag_found:
            analysis += " Signature mentioned but not filled."
            signature_issues.append(i + 1)

        results.append(f"Page {i+1}: {analysis}")

    doc.close()

    summary = {
        "total_pages": num_pages,
        "signature_issues": signature_issues
    }

    return summary, results

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            summary, report = analyze_pdf_with_llama3(filepath)
            return render_template('result.html', report=report, filename=filename, summary=summary)

        return redirect(request.url)

    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True, host="192.168.0.205")
