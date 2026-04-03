from dotenv import load_dotenv
load_dotenv()
import os
import re
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from PIL import Image
from dateutil import parser
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import json
from flask_cors import CORS
from database import engine, Base, SessionLocal
from models import DocumentAnalysis
import requests
import time
from openai import OpenAI

# ===============================
# FLASK SETUP
# ===============================
app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
CORS(app) 
OCR_API_KEY = os.getenv("OCR_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===============================
# OCR & INFORMATION EXTRACTION
# ===============================
def extract_text_from_image(file_obj):
    filename = file_obj.filename if file_obj.filename else "upload.jpg"

    response = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": (filename, file_obj)},
        data={
            "apikey": OCR_API_KEY,
            "language": "eng",
            "isOverlayRequired": False,
        },
    )

    result = response.json()
    if result.get("IsErroredOnProcessing"):
        return ""
    try:
        return result["ParsedResults"][0]["ParsedText"]
    except:
        return ""

def extract_json_from_text(text):
    """
    Extract the first JSON object in the text.
    """
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            return {"error": "No JSON found in output", "raw_output": text}
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON", "raw_output": text}

def extract_from_ocr(ocr_text):
    """
    Extract structured fields from OCR text using OpenAI (lightweight model).
    """

    prompt = f"""
You are a strict information extraction system.

Extract the following fields from the text:

- passenger_name
- flight_number
- train_number
- travel_date

Return ONLY valid JSON in this format:
{{
  "passenger_name": null,
  "flight_number": null,
  "train_number": null,
  "travel_date": null
}}

Rules:
- Output ONLY JSON
- No explanation
- Use null if missing

Text:
\"\"\"{ocr_text}\"\"\"
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You extract structured data from text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        output_text = response.choices[0].message.content.strip()

        # Parse JSON safely
        try:
            return json.loads(output_text)
        except json.JSONDecodeError:
            return {
                "error": "JSON parse failed",
                "raw_output": output_text
            }

    except Exception as e:
        return {"error": str(e)}

def extract_information(text):
    """
    Extract structured information from OCR text using NLP Cloud,
    keeping database error handling and status logic unchanged.
    """
    data = {
        "passenger_name": None,
        "flight_number": None,
        "train_number": None,
        "travel_date": None,
        "errors": []
    }

    try:
        # Use NLP Cloud to extract structured info
        nlp_result = extract_from_ocr(text)

        # Check if NLP Cloud returned an error
        if "error" in nlp_result:
            data["errors"].append(nlp_result.get("error"))
            if "raw_output" in nlp_result:
                data["errors"].append(f"Raw NLP output: {nlp_result['raw_output']}")
        else:
            # Fill data from NLP Cloud response
            data["passenger_name"] = nlp_result.get("passenger_name")
            data["flight_number"] = nlp_result.get("flight_number")
            data["train_number"] = nlp_result.get("train_number")
            travel_date = nlp_result.get("travel_date")

            if travel_date:
                # Check if a 4-digit year is present
                if re.search(r"\b\d{4}\b", travel_date):
                    # Parse normally if year exists
                    try:
                        parsed_date = parser.parse(travel_date, fuzzy=True)
                        data["travel_date"] = parsed_date.strftime("%Y-%m-%d")
                    except Exception:
                        data["travel_date"] = travel_date
                        data["errors"].append("Travel date parsing failed")
                else:
                    # Only day+month, keep as-is, mark missing year
                    data["travel_date"] = travel_date
                    data["errors"].append("Travel date missing year")
            else:
                data["errors"].append("Travel date not found")

            # Only passenger_name is mandatory
            if not data["passenger_name"]:
                data["errors"].append("Passenger name not found")

    except Exception as e:
        data["errors"].append(f"Extraction failed: {str(e)}")

    return data
# ===============================
# ROUTES
# ===============================
@app.route("/", methods=["GET"])
def home():
    return "Backend running!"

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    filename = file.filename if file.filename else "unknown_file"
    # OCR directly from memory (NO saving)
    extracted_text = extract_text_from_image(file)

    print("extracted_text: ", extracted_text)

    # Extract structured info
    result = extract_information(extracted_text)
    print("errors: ",result["errors"])
    # ===============================
    # Handle errors
    # ===============================
    if result["errors"]:
        db = SessionLocal()

        record = DocumentAnalysis(
            passenger_name=result.get("passenger_name"),
            flight_number=result.get("flight_number"),
            train_number=result.get("train_number"),
            travel_date=None,
            status="error",
            error_message=", ".join(result["errors"]),
            file_path=filename
        )

        db.add(record)
        db.commit()
        db.close()

        result["status"] = "error"
        return jsonify(result)

    # ===============================
    # Determine status
    # ===============================
    travel_date_obj = None
    if result.get("travel_date"):
        try:
            travel_date_obj = datetime.strptime(result["travel_date"], "%Y-%m-%d")
        except:
            travel_date_obj = None

    if travel_date_obj and travel_date_obj.year < 2025:
        status = "rejected"
    else:
        status = "approved"

    # ===============================
    # Save to DB
    # ===============================
    db = SessionLocal()

    record = DocumentAnalysis(
        passenger_name=result.get("passenger_name"),
        flight_number=result.get("flight_number"),
        train_number=result.get("train_number"),
        travel_date=travel_date_obj,
        status=status,
        file_path=filename 
    )

    db.add(record)
    db.commit()
    db.close()

    # ===============================
    # Return result
    # ===============================
    result["status"] = status
    return jsonify(result)

@app.route("/dashboard", methods=["GET"])
def dashboard():
    db = SessionLocal()
    results = db.query(DocumentAnalysis).order_by(DocumentAnalysis.created_at.desc()).all()
    db.close()

    total = len(results)
    approved = sum(1 for r in results if r.status == "approved")
    rejected = sum(1 for r in results if r.status == "rejected")
    error = sum(1 for r in results if r.status == "error")

    records = []
    for r in results:
        records.append({
            "id": r.id,
            "passengerName": r.passenger_name,
            "travelDate": r.travel_date.strftime("%Y-%m-%d") if r.travel_date else None,
            "status": r.status,
            "submittedDate": r.created_at.date().isoformat(),
            "documentName": os.path.basename(r.file_path) if r.file_path else None
        })

    return jsonify({
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "error": error,
        "records": records
    })

if __name__ == "__main__":
    app.run(debug=True)