from flask import Flask, request, render_template, redirect
import os
import fitz  # PyMuPDF
import requests
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}

# --- Function 1: Signature Check via PDF Tags ---
def check_signatures(pdf_path):
    signature_issues = []

    with open(pdf_path, "rb") as f:
        raw_data = f.read()
        signature_tag_found = any(tag in raw_data for tag in [
            b"<</Subtype/page/Type/FillSignData>>",
            b"/Sig",
            b"/Signature"
        ])

    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text().lower()
        page_number = i + 1
        if "signature" in text and not signature_tag_found:
            signature_issues.append(f"Signature mentioned but not filled on Page {page_number}")
    doc.close()

    return signature_issues

# --- Function 2: Analyze PDF Content via LLaMA ---
def analyze_with_llama(pdf_path):
    doc = fitz.open(pdf_path)
    analysis_report = {
        "Unanswered Questions/Activities": [],
        "Missing Sections": []
    }

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        page_number = i + 1

        prompt = f"""
You are evaluating a learner's Portfolio of Evidence (PoE) PDF.

Your task is to carefully analyze the text and identify **specific issues** such as:
- Unanswered or incomplete questions or activities (e.g., "Question No. 3", "Activity 2.1", etc.)
- Missing critical sections such as:
    - Reflection
    - Logbook
    - Critical Cross-Field Outcomes (CCFO)
    - Declaration of Authenticity
- Use indicators such as:
    - "Click or tap here to enter text"
    - "Enter answer here"
    - Sections present with no input
    - Obvious gaps in expected learner input

Return the result in this exact structure (only list items that apply):

Unanswered Questions/Activities:
- Page {page_number}: Question/Activity Description ➜ Indicator

Missing Sections:
- Page {page_number}: Section Name ➜ Description of what's missing

If everything is completed on this page, return:
All fields appear to be completed on Page {page_number}.

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
            result = response.json().get("response", "").strip()
        except Exception as e:
            result = f"Error on page {page_number}: {str(e)}"

        if "All fields appear to be completed" not in result:
            # Split into categories manually
            for line in result.splitlines():
                if line.strip().startswith("- Page") and "Question" in line:
                    analysis_report["Unanswered Questions/Activities"].append(line.strip())
                elif line.strip().startswith("- Page") and "Section" in line:
                    analysis_report["Missing Sections"].append(line.strip())

    doc.close()
    return analysis_report

# --- Flask routes ---
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            signature_issues = check_signatures(filepath)
            llama_report = analyze_with_llama(filepath)

            full_report = {
                "Unanswered Questions/Activities": llama_report["Unanswered Questions/Activities"],
                "Missing Sections": llama_report["Missing Sections"],
                "Signature Issues": signature_issues
            }

            return render_template('result.html', report=full_report, filename=filename)

        return redirect(request.url)
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True, host='192.168.0.205')
