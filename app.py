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

    # Check for signature tags more broadly
    with open(pdf_path, "rb") as f:
        raw_data = f.read()
        signature_tag_found = any(tag in raw_data for tag in [
            b"<</Subtype/page/Type/FillSignData>>",
            b"/Sig",
            b"/Signature"
        ])

    for i in range(num_pages):
        page = doc.load_page(i)
        text = page.get_text()

        # Manual fallback detection
        unanswered_flags = ["click or tap here", "enter answer here", "type here", "add response", "student to complete"]
        unanswered_detected = [line.strip() for line in text.lower().splitlines() if any(flag in line for flag in unanswered_flags)]

        # Prompt for LLaMA3
        prompt = f"""
You are a POE (Portfolio of Evidence) evaluator reviewing a student's submission.

Instructions:
- Identify unanswered questions or activities. These may be labeled like "Question No. 1", "Activity 2.1", etc., and considered unanswered if:
  * They contain text such as "Click or tap here to enter text", "Enter answer here", "Type here", or similar.
  * They are followed by blank space or no meaningful student input.
- Identify missing sections such as: Reflection, Logbook, CCFO, or Declaration.
- Identify if any signature is expected (e.g. labeled "Signature") but not filled.

Respond ONLY in this exact format, even if empty:

Unanswered Questions/Activities:
- ...

Missing Sections:
- ...

Signature Issues:
- ...

If all fields are completed, respond with:
All fields appear to be completed.

## Start of Page Text
{text}
## End of Page Text

Do not explain or summarize. Only use the above format.
"""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3:8b-q4_K_M", "prompt": prompt, "stream": False},
                timeout=60
            )
            analysis = response.json().get("response", "").strip()

            # Fallback if AI output is empty
            if not analysis:
                analysis = "No response from model."

        except Exception as e:
            analysis = f"Error analyzing page {i+1}: {str(e)}"

        # Add manual detections if found
        if unanswered_detected and "Unanswered Questions/Activities" not in analysis:
            if "All fields appear to be completed." in analysis:
                analysis = analysis.replace("All fields appear to be completed.", "")
            analysis += "\nUnanswered Questions/Activities:\n"
            for line in unanswered_detected:
                analysis += f"- Possible unanswered field: '{line}'\n"

        # Additional signature check
        if "signature" in text.lower() and not signature_tag_found:
            analysis += "\nSignature Issues:\n- Signature mentioned but not filled."
            signature_issues.append(i + 1)

        # Log output for debugging
        print(f"\n=== Page {i+1} ===")
        print(analysis)

        results.append(f"<strong>Page {i+1}</strong>:<br>{analysis.replace('\n', '<br>')}")

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
