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
        "Unanswered Questions/Activities": [],
        "Missing Sections": [],
        "Signature Issues": []
    }

    def is_blank_or_placeholder(text):
        patterns = [
            r"click or tap here to enter text",
            r"enter answer here",
            r"answer to \d+\.\d*",
            r"learner response",
            r"click or tap to enter a date",
            r"choose\s+an\s+item",
            r"enter text here",
        ]
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    def extract_unanswered_questions(text, label):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if is_blank_or_placeholder(line):
                context = lines[i-1].strip() if i > 0 else "?"
                results["Unanswered Questions/Activities"].append(f"{label}: {context} ➜ {line.strip()}")

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        page_number = i + 1

        # Check for unanswered fields
        if re.search(r"(question|activity|answer)\s+no?\.?", text, re.IGNORECASE) or is_blank_or_placeholder(text):
            extract_unanswered_questions(text, f"Page {page_number}")

        # Signature issues
        if "signature" in text.lower():
            if re.search(r"signature\s*:?[\s\n]*$", text.lower()) or is_blank_or_placeholder(text):
                results["Signature Issues"].append(f"Page {page_number}: Signature mentioned but not filled.")

        # Missing sections
        if "reflection" in text.lower() and "enter answer here" in text.lower():
            results["Missing Sections"].append("Reflection is not completed")
        if "logbook" in text.lower() and "enter answer here" in text.lower():
            results["Missing Sections"].append("Logbook is not completed")
        if "critical cross field outcomes" in text.lower() and "enter answer here" in text.lower():
            results["Missing Sections"].append("CCFO outcomes are not completed")
        if "declaration" in text.lower() and is_blank_or_placeholder(text):
            results["Missing Sections"].append("Declaration section not filled")

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
