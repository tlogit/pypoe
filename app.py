from flask import Flask, request, render_template, redirect
import os
import fitz  # PyMuPDF
from werkzeug.utils import secure_filename
import re

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

    current_section = None
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        lines = text.splitlines()
        page_number = i + 1

        for idx, line in enumerate(lines):
            lower_line = line.lower().strip()

            # Detect section context
            if "formative assessment for" in lower_line:
                current_section = "Formative"
            elif "summative assessment" in lower_line or "workplace assessments" in lower_line:
                current_section = "Summative"
            elif "reflection" in lower_line:
                current_section = "Reflection"
            elif "logbook" in lower_line:
                current_section = "Logbook"
            elif "critical cross field outcomes" in lower_line:
                current_section = "CCFO"
            elif "declaration of authenticity" in lower_line or "submission & remediation" in lower_line:
                current_section = "Declaration"
            elif "signature" in lower_line:
                current_section = "Signature"

            # Check for unanswered fields
            if is_placeholder(line):
                context = lines[idx - 1] if idx > 0 else "?"
                item = f"{context.strip()} ➜ {line.strip()} (Page {page_number})"

                if current_section == "Formative":
                    results["Unanswered Formative Questions"].append(item)
                elif current_section == "Summative":
                    results["Unanswered Summative Questions"].append(item)
                elif current_section == "Reflection":
                    results["Missing Sections"].append("Reflection section is incomplete.")
                elif current_section == "Logbook":
                    results["Missing Sections"].append("Logbook entries are incomplete.")
                elif current_section == "CCFO":
                    results["Missing Sections"].append("CCFO evidence is incomplete.")
                elif current_section == "Declaration":
                    results["Missing Sections"].append("Declaration not signed or filled.")
                elif current_section == "Signature":
                    results["Signature Issues"].append(f"Signature field not filled on Page {page_number}.")

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
