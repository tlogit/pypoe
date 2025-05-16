from flask import Flask, request, render_template, redirect
import os
import fitz  # PyMuPDF
from werkzeug.utils import secure_filename
from langchain.llms import Ollama
from langchain.prompts import PromptTemplate

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- Signature Detection ----------
def check_signatures(pdf_path):
    signature_issues = []
    with open(pdf_path, "rb") as f:
        raw_data = f.read()
        signature_tag_found = any(tag in raw_data for tag in [
            b"<</Subtype/page/Type/FillSignData>>", b"/Sig", b"/Signature", b"/FillSignData"
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

# ---------- Section Extraction ----------
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
        lower = text.lower()
        if "formative assessment for" in lower:
            current_section = "Formative"
        elif "summative assessment" in lower or "workplace assessments" in lower:
            current_section = "Summative"
        elif "reflection" in lower:
            current_section = "Reflection"
        elif "logbook" in lower:
            current_section = "Logbook"
        elif "critical cross field outcomes" in lower:
            current_section = "CCFO"
        elif "declaration of authenticity" in lower or "submission & remediation" in lower:
            current_section = "Declaration"
        if current_section:
            sections[current_section] += "\n\n" + text
    doc.close()
    return sections

# ---------- Chunking ----------
def chunk_text(text, chunk_size=4000, overlap=250):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunk = " ".join(words[start:start+chunk_size])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks

# ---------- Confidence Scoring ----------
def determine_confidence(text):
    text = text.lower()
    if any(k in text for k in ["click or tap", "enter answer here", "answer to", "type here"]):
        return "High"
    elif any(k in text for k in ["blank", "no input", "not filled", "empty"]):
        return "Medium"
    return "Low"

# ---------- LLaMA Analysis ----------
PROMPT_TEMPLATE = PromptTemplate.from_template("""
You are an assessor reviewing a section of a student's Portfolio of Evidence (PoE).

Identify:
- Unanswered or incomplete questions (e.g., "Question 3.1", "Activity 2.4")
- Entire sections that are present but blank (e.g., Reflection, Logbook, CCFO, Declaration)

Look for signs like:
- "Click or tap here to enter text"
- "Enter answer here"
- "Answer to X.X"
- Blank or placeholder text
- Headings with no learner input

Only return:

Unanswered Questions/Activities:
- [Item] ➜ [Reason]

Missing Sections:
- [Item] ➜ [Reason]

TEXT START
{content}
TEXT END
""")

def analyze_with_llama(pdf_path):
    sections = extract_sections(pdf_path)
    analysis = {
        "Unanswered Questions/Activities": [],
        "Missing Sections": []
    }
    llama = Ollama(model="llama3")

    for section, content in sections.items():
        if not content.strip():
            continue
        chunks = chunk_text(content)
        seen = set()

        for i, chunk in enumerate(chunks):
            prompt = PROMPT_TEMPLATE.format(section=section, content=chunk)
            try:
                result = llama(prompt).strip()
                print(f"\n=== LLaMA OUTPUT for {section} Chunk {i+1} ===\n{result}\n")
            except Exception as e:
                result = f"Error: {e}"

            for line in result.splitlines():
                if line.strip().startswith("- ") and "➜" in line:
                    clean_line = f"{section}: {line.strip()[2:]}"
                    if clean_line in seen:
                        continue
                    seen.add(clean_line)
                    conf = determine_confidence(line)
                    entry = f"{clean_line} [Confidence: {conf}]"
                    if any(k in line.lower() for k in ["reflection", "logbook", "ccfo", "declaration"]):
                        analysis["Missing Sections"].append(entry)
                    else:
                        analysis["Unanswered Questions/Activities"].append(entry)
    return analysis

# ---------- File Type Check ----------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}

# ---------- Flask Routes ----------
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
                "Unanswered Questions/Activities": llama_report["Unanswered Questions/Activities"] or ["No issues found."],
                "Missing Sections": llama_report["Missing Sections"] or ["No issues found."],
                "Signature Issues": signature_issues or ["No issues found."]
            }

            return render_template('result.html', report=full_report, filename=filename)
        return redirect(request.url)
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True, host='192.168.0.205')
