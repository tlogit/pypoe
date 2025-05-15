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
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Signature Detection ---
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

# --- Section Extraction ---
def extract_sections(pdf_path):
    doc = fitz.open(pdf_path)
    sections = {
        "Formative": "",
        "Summative": "",
        "Reflection": "",
        "Logbook": "",
        "CCFO": "",
        "Declaration": ""
    }

    current_section = None
    for page in doc:
        text = page.get_text().strip()
        lower_text = text.lower()

        if "formative assessment for" in lower_text:
            current_section = "Formative"
        elif "summative assessment" in lower_text or "workplace assessments" in lower_text:
            current_section = "Summative"
        elif "reflection" in lower_text:
            current_section = "Reflection"
        elif "logbook" in lower_text:
            current_section = "Logbook"
        elif "critical cross field outcomes" in lower_text:
            current_section = "CCFO"
        elif "declaration of authenticity" in lower_text or "submission & remediation" in lower_text:
            current_section = "Declaration"

        if current_section:
            sections[current_section] += "\n\n" + text

    doc.close()
    return sections

# --- LLaMA-Based Section Analysis ---
def analyze_with_llama(pdf_path):
    sections_text = extract_sections(pdf_path)
    analysis_report = {
        "Unanswered Questions/Activities": [],
        "Missing Sections": []
    }

    for section, content in sections_text.items():
        if not content.strip():
            continue

        prompt = f"""
You are an assessor reviewing the '{section}' section of a student's Portfolio of Evidence (PoE). Your job is to identify any **missing or unanswered** content.

❗ Your tasks:
- Detect unanswered questions (e.g., "Question 3.1", "Activity 2.4") with phrases like:
  - "Click or tap here to enter text"
  - "Enter answer here"
  - "Answer to X.X"
  - Any obvious placeholders
  - Headings with no responses below them
- Mark entire sections (e.g., Reflection, Logbook, CCFO, Declaration) as missing if they:
  - Contain only placeholders or blanks
  - Are clearly not filled in

Respond strictly in this format:

Unanswered Questions/Activities:
- [Question or Activity] ➜ [Why it is unanswered]

Missing Sections:
- [Section] ➜ [Why it is missing]

TEXT START
{content}
TEXT END
"""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3:8b-q4_K_M", "prompt": prompt, "stream": False},
                timeout=120
            )
            result = response.json().get("response", "").strip()
        except Exception as e:
            result = f"Error analyzing {section} section: {str(e)}"

        # Log output for debugging
        print(f"\n=== LLaMA OUTPUT FOR SECTION: {section} ===\n{result}\n")

        # Extract bullet points
        if "appear completed" not in result.lower():
            for line in result.splitlines():
                line = line.strip()
                if line.startswith("- ") and "➜" in line:
                    if any(key in line.lower() for key in ["reflection", "logbook", "ccfo", "declaration"]):
                        analysis_report["Missing Sections"].append(f"{section}: {line[2:]}")
                    else:
                        analysis_report["Unanswered Questions/Activities"].append(f"{section}: {line[2:]}")
    return analysis_report

# --- Flask Routes ---
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
                "Unanswered Questions/Activities": llama_report["Unanswered Questions/Activities"] or ["No issues found in this section."],
                "Missing Sections": llama_report["Missing Sections"] or ["No issues found in this section."],
                "Signature Issues": signature_issues or ["No issues found in this section."]
            }

            return render_template('result.html', report=full_report, filename=filename)

        return redirect(request.url)
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True, host='192.168.0.205')
