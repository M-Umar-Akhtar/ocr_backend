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
import nlpcloud

# ===============================
# FLASK SETUP
# ===============================
app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
CORS(app) 
OCR_API_KEY = os.getenv("OCR_API_KEY")
NLP_CLOUD_KEY = os.getenv("NLP_CLOUD_KEY")
# ===============================
# DATABASE SETUP (SQLAlchemy)
# ===============================

#Base.metadata.create_all(bind=engine)
client = nlpcloud.Client("finetuned-llama-3-70b", NLP_CLOUD_KEY, gpu=True)

# ===============================
# OCR & INFORMATION EXTRACTION
# ===============================
def extract_text_from_image(image_path):
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": f},
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

# def extract_information(text):
#     data = {
#         "passenger_name": None,
#         "flight_number": None,
#         "train_number": None,
#         "travel_date": None,
#         "errors": []
#     }

#     lines = [line.strip() for line in text.split("\n") if line.strip()]

#     # ---- Train Number ----
#     train_match = re.search(r"\b\d{4,5}\s*/\s*[A-Z\s]{3,}\b", text.upper())
#     if train_match:
#         data["train_number"] = train_match.group().replace(" ", "")

#     # ---- Flight Number ----
#     flight_match = re.search(r"\b[A-Z]{2,3}\s?\d{2,4}\b", text.upper())
#     if flight_match:
#         data["flight_number"] = flight_match.group().replace(" ", "")

#     # ---- Travel Date ----
#     normalized_text = re.sub(r"\bI{1,3}\b", lambda m: str(len(m.group())), text.upper())
#     date_patterns = [
#         r"\b\d{1,2}[-/][A-Z]{3}[-/]\d{2,4}\b",          # 9-OCT-2013
#         r"\b\d{1,2}\s[A-Z]{3}\s\d{2,4}\b",              # 9 OCT 2013
#         r"\b\d{4}[-/]\d{2}[-/]\d{2}\b",                 # 2013-10-09
#         r"\b[A-Z]{3,9}\s\d{1,2},?\s\d{4}\b",            # OCTOBER 9 2013
#         r"\d{1,2}\s(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)",     # 09 OCT
#         r"\b\d{1,2}(?:st|nd|rd|th)?\s[A-Z]{3,9}\b"
#     ]

#     found_dates = []
#     for pattern in date_patterns:
#         found_dates.extend(re.findall(pattern, normalized_text))

#     # Prefer date near "Departure"
#     departure_lines = [line for line in lines if "DEPARTURE" in line.upper()]
#     date_found = None
#     for dline in departure_lines:
#         for pattern in date_patterns:
#             m = re.findall(pattern, dline.upper())
#             if m:
#                 date_found = m[0]
#                 break
#         if date_found:
#             break
#     if not date_found and found_dates:
#         date_found = found_dates[0]

#     if date_found:
#     # Check if year is present
#         if re.search(r"\b\d{4}\b", date_found):
#             try:
#                 parsed_date = parser.parse(date_found, fuzzy=True)
#                 if parsed_date.year < 100:
#                     parsed_date = parsed_date.replace(year=2000 + parsed_date.year)
#                 data["travel_date"] = parsed_date.strftime("%Y-%m-%d")
#             except Exception:
#                 data["errors"].append("Invalid date format")
#         else:
#             data["travel_date"] = date_found
#             data["errors"].append("Travel date missing year")
#     else:
#         data["errors"].append("Travel date not found")

#     # ---- Passenger Name ----
#     blacklist_words = [
#         "AIRLINES", "AIRWAYS", "AIR", "INTERNATIONAL",
#         "FLIGHT", "BOARDING", "GATE", "TIME", "CHECK",
#         "TERMINAL", "DEPARTURE", "ARRIVAL", "RESERVATION", "SLIP", "ELECTRONIC", "USER","BUSINESS"
#     ]

#     name_found = False
#     for i, line in enumerate(lines):
#         if "# NAME" in line.upper() or "PASSENGER" in line.upper():
#             parts = line.split(":")
#             candidate = parts[1].strip() if len(parts) > 1 else (lines[i+1].strip() if i+1 < len(lines) else "")
#             candidate = candidate.upper()
#             if candidate and not any(word in candidate for word in blacklist_words):
#                 data["passenger_name"] = candidate
#                 name_found = True
#                 break

#     if not name_found:
#         for line in lines:
#             clean_line = line.strip().upper()
#             if (clean_line.isupper() and 2 <= len(clean_line.split()) <= 3 and
#                 not any(word in clean_line for word in blacklist_words) and
#                 not re.search(r"\d", clean_line)):
#                 data["passenger_name"] = clean_line
#                 break

#     if not data["passenger_name"]:
#         data["errors"].append("Passenger name not found")

#     return data


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
    Extract passenger_name, flight_number, train_number, travel_date from OCR text
    using finetuned-llama-3-70b and structured JSON prompt.
    """
    try:
        # Prepare the prompt
        prompt = f"""
Extract the following fields from the text below:

- passenger_name
- flight_number
- train_number
- travel_date

Text: \"\"\"{ocr_text}\"\"\"

Return the output in valid JSON format with keys exactly:
passenger_name, flight_number, train_number, travel_date. 
If a field is not present, set its value to null.
"""

        # Call the model
        response = client.generation(prompt, max_length=300)
        output_text = response.get("generated_text", "").strip()

        # Try to parse JSON from the model's output
        try:
            data = extract_json_from_text(output_text)
        except json.JSONDecodeError:
            # If parsing fails, return raw text for debugging
            data = {"error": "Failed to parse JSON", "raw_output": output_text}
        print("Model response: ",data)
        return data

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

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(filepath)
    print("Before OCR")
    # OCR
    extracted_text = extract_text_from_image(filepath)
    print("extracted_text: ",extracted_text)
    # Extract structured info

    result = extract_information(extracted_text)
    print("After")
    # ===============================
    # Determine status & save if no errors
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
            file_path=filepath
        )

        db.add(record)
        db.commit()
        db.close()

        result["status"] = "error"
        return jsonify(result)

    travel_date_obj = datetime.strptime(result["travel_date"], "%Y-%m-%d") if result.get("travel_date") else None
    if travel_date_obj and travel_date_obj.year < 2025:
        status = "rejected"
    else:
        status = "approved"

    # Save to DB
    db = SessionLocal()
    record = DocumentAnalysis(
        passenger_name=result.get("passenger_name"),
        flight_number=result.get("flight_number"),
        train_number=result.get("train_number"),
        travel_date=travel_date_obj,
        status=status,
        file_path=filepath  # <-- save file path here
    )
    db.add(record)
    db.commit()
    db.close()

    # Return result with status
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