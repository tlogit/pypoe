from flask import Flask, request, render_template, redirect
import os
import fitz  # PyMuPDF
import re
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def analyze_pdf_like_chatgpt(pdf_path):
    doc = fitz.open(pdf_path)

    results = {
        "Unanswered Formative Questions": [],
        "Unanswered Summative Questions": [],
        "Missing Sections": [],
        "Signature Issues": []
    }

    signature_pages_seen = set()
    sections_found = {
        "Reflection": False,
        "Logbook": False,
        "CCFO": False,
        "Declaration": False
    }

    current_section = None
    seen_placeholders = set()

    def is_placeholder(text):
        patterns = [
            r"click or tap here to enter text",
            r"enter answer here",
            r"answer to \d+",
            r"learner response",
            r"choose\s+an\s+item",
            r"click or tap to enter a date",
            r"enter text here"
        ]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        lines = text.splitlines()
        page_number = i + 1

        for idx, line in enumerate(lines):
            lower_line = line.lower().strip()

            # Detect section
            if "formative assessment for" in lower_line:
                current_section = "Formative"
            elif "summative assessment" in lower_line or "workplace assessments" in lower_line:
                current_section = "Summative"
            elif "reflection" in lower_line:
                current_section = "Reflection"
                sections_found["Reflection"] = True
            elif "logbook" in lower_line:
                current_section = "Logbook"
                sections_found["Logbook"] = True
            elif "critical cross field outcomes" in lower_line:
                current_section = "CCFO"
                sections_found["CCFO"] = True
            elif "declaration of authenticity" in lower_line or "submission & remediation" in lower_line:
                current_section = "Declaration"
                sections_found["Declaration"] = True

            # Placeholder fields
            if is_placeholder(line):
                context = lines[idx - 1] if idx > 0 else ""
                field_id = f"{context.strip()}|{page_number}"

                if field_id in seen_placeholders:
                    continue  # Avoid duplicates
                seen_placeholders.add(field_id)

                item = f"{context.strip()} ➜ {line.strip()} (Page {page_number})"

                if current_section == "Formative":
                    results["Unanswered Formative Questions"].append(item)
                elif current_section == "Summative":
                    results["Unanswered Summative Questions"].append(item)
                elif current_section in ["Reflection", "Logbook", "CCFO", "Declaration"]:
                    label = {
                        "Reflection": "Reflection section is incomplete.",
                        "Logbook": "Logbook entries are incomplete.",
                        "CCFO": "CCFO evidence is incomplete.",
                        "Declaration": "Declaration not signed or filled."
                    }.get(current_section)
                    if label and label not in results["Missing Sections"]:
                        results["Missing Sections"].append(label)

            # Signature fields
            if "signature" in lower_line and page_number not in signature_pages_seen:
                if is_placeholder(line):
                    results["Signature Issues"].append(f"Missing signature on Page {page_number}")
                    signature_pages_seen.add(page_number)

    # If any section was found but not completed, enforce that once
    for section, seen in sections_found.items():
        if seen:
            label = {
                "Reflection": "Reflection section is incomplete.",
                "Logbook": "Logbook entries are incomplete.",
                "CCFO": "CCFO evidence is incomplete.",
                "Declaration": "Declaration not signed or filled."
            }[section]
            if label not in results["Missing Sections"]:
                results["Missing Sections"].append(label)

    doc.close()
    return results

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            report = analyze_pdf_like_chatgpt(filepath)
            return render_template('result.html', report=report, filename=filename)

        return redirect(request.url)
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True, host='192.168.0.205')
