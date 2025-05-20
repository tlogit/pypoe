import os
import datetime
import fitz  # PyMuPDF
from transformers import LlamaTokenizer, LlamaForCausalLM, Trainer, TrainingArguments, TextDataset
from datasets import Dataset
import torch

# === Step 1: Extract Text from PDF ===
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    full_text = "\n".join(page.get_text() for page in doc)
    return full_text

# === Step 2: Preprocess the Text ===
def preprocess_text(text):
    # Split by SAQA ID or similar headers if pattern known
    chunks = text.split("SAQA ID")
    processed = ["SAQA ID" + chunk.strip() for chunk in chunks if chunk.strip()]
    return processed

# === Step 3: Prepare Dataset ===
def prepare_dataset(chunks):
    return Dataset.from_dict({"text": chunks})

# === Step 4: Fine-tune LLaMA 3 ===
def fine_tune_model(dataset):
    model_name = "meta-llama/Llama-3-8b"  # HuggingFace-style
    tokenizer = LlamaTokenizer.from_pretrained(model_name)
    model = LlamaForCausalLM.from_pretrained(model_name, device_map="auto", torch_dtype=torch.float16)

    def tokenize_function(examples):
        return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)

    tokenized_datasets = dataset.map(tokenize_function, batched=True)
    
    training_args = TrainingArguments(
        output_dir="./results",
        per_device_train_batch_size=2,
        num_train_epochs=1,
        logging_dir="./logs",
        save_strategy="no",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets,
        tokenizer=tokenizer,
    )

    trainer.train()

# === Step 5: Main Runner ===
def run_daily_training():
    pdf_path = "PoE - SD5 - SP7 - Ver.04.24.P.pdf"
    text = extract_text_from_pdf(pdf_path)
    chunks = preprocess_text(text)
    dataset = prepare_dataset(chunks)
    fine_tune_model(dataset)

# === Step 6: Scheduler Setup ===
if __name__ == "__main__":
    print(f"[{datetime.datetime.now()}] Starting daily training...")
    run_daily_training()
    print("Training complete.")
