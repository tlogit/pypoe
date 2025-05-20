import os
import re
import json
import datetime
import fitz  # PyMuPDF
import subprocess

# === CONFIG ===
INPUT_PDF = "PoE_-_SD5_-_SP7_-_Ver.04.24.P.pdf"
OUTPUT_DIR = "daily_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === STEP 1: Extract Text from PDF ===
def extract_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)

# === STEP 2: Chunk by Unit Standard Titles ===
def chunk_text_by_unit_standards(text):
    pattern = r"(Unit standard title:.*?)(?=Unit standard title:|$)"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    return matches

# === STEP 3: Run LLaMA 3 via Ollama to Summarize Text ===
def summarize_with_llama(chunk):
    prompt = f"Summarize this training unit for easy learning:\n\n{chunk.strip()}\n\nSummary:"
    try:
        result = subprocess.run(
            ["ollama", "run", "llama3", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[Error] {e}"

# === STEP 4: Save Output as JSON ===
def save_output(data, date_str):
    file_path = os.path.join(OUTPUT_DIR, f"poe_summary_{date_str}.json")
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[✔] Saved summary to {file_path}")

# === MAIN RUNNER ===
def run_daily_poe_processing():
    print("[⏳] Extracting PDF...")
    raw_text = extract_text(INPUT_PDF)
    chunks = chunk_text_by_unit_standards(raw_text)

    print(f"[🔍] Found {len(chunks)} unit standard sections.")
    summaries = []
    for i, chunk in enumerate(chunks):
        print(f"[🤖] Summarizing chunk {i+1}...")
        summary = summarize_with_llama(chunk)
        summaries.append({
            "unit_index": i + 1,
            "summary": summary,
            "original_length": len(chunk)
        })

    today = datetime.date.today().isoformat()
    save_output(summaries, today)
    print("[✅] Daily PoE processing complete.")

# === ENTRY POINT ===
if __name__ == "__main__":
    run_daily_poe_processing()
