from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
import os
import time
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
from dotenv import load_dotenv
import datetime
import pdfkit
from openai import AzureOpenAI
import shutil
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# Azure Key Vault details
key_vault_name = 'AI-vault-hepta'
key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"

# Authenticate to Azure Key Vault
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)

# Load environment variables
load_dotenv()

# Initialize Azure OpenAI client
azure_api_key = secret_client.get_secret('AZUREopenaiAPIkey').value
azure_endpoint = secret_client.get_secret("AZUREopenaiENDPOINT").value
reformulate_deployment = 'IndexSelector'
insert_deployment = 'IndexSelector'
openai_client = AzureOpenAI(api_key=azure_api_key, api_version="2024-02-15-preview", azure_endpoint=azure_endpoint)

# Configure pdfkit to point to your wkhtmltopdf installation
path_to_wkhtmltopdf = os.getenv("PATH_TO_WKHTMLTOPDF")
config = pdfkit.configuration(wkhtmltopdf=path_to_wkhtmltopdf)

def extract_text(file_path):
    try:
        if file_path.lower().endswith(".pdf"):
            with fitz.open(file_path) as doc:
                return " ".join(page.get_text() for page in doc)
        elif file_path.lower().endswith(".docx"):
            doc = Document(file_path)
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        else:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image)
    except Exception as e:
        print(f"Error extracting text: {e}")
        return None

def reformulate_text(text):
    prompt = f"Extract from the following text these information in the form of a list: full name, job title, years of experience(based on the date range or ranges), phone, email, website, tech tools, tasks, mission or missions, date range or ranges, company name or names.\n\n{text}"
    try:
        response = openai_client.completions.create(
            model=reformulate_deployment,
            prompt=prompt,
            max_tokens=1500
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print(f"Error in generating completion: {e}")
        return None

def insert_text_into_template(structured_data, image_url):
    prompt = f"""Insert the following structured data into the HTML template that has variables for each section and generate the exact same template with the structured data inserted. GENERATE ONLY THE FILLED TEMPLATE:

Structured Data:
{structured_data}

Template:
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CV with Background Banner</title>
    <style>
        body {{
            font-family: 'Open Sans', sans-serif;
            margin: 0;
            padding: 0;
            background: white;
        }}
        .banner {{
            background-image: url('{image_url}');
            background-size: cover;
            background-position: center;
            height: 235px;
            color: white;
            position: relative;
            top: 0;
        }}
        .job-title {{
            font-size: 20pt;
            font-weight: bold;
            text-align: center;
            padding-top: 50px;
        }}
        .contact-strip {{
            background-color: #01cdb1;
            height: 30px;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .contact-info {{
            font-size: 10pt;
            display: flex;
            justify-content: center;
            gap: 10px;
            color: black;
        }}
        .contact-icon {{
            margin-right: 3px;
        }}
        .section {{
            font-family: 'Open Sans', sans-serif;
            margin-top: 20px;
            padding: 0 20px;
            background: white;
        }}
        .section-title {{
            text-align: center;
            color: #01cdb1;
            font-size: 20pt;
            margin: 30px 0;
        }}
        .section-content {{
            color: #050b24;
            padding-bottom: 20px;
        }}
        .company-name {{
            float: right;
            margin-right: 50px;
        }}
        .date-range,
        .tasks,
        .mission,
        .tech-tools {{
            margin-left: 50px;
        }}
        .sub-section {{
            margin-top: 20px;
        }}
        .sub-section-title {{
            font-size: 16pt;
            font-weight: bold;
            color: #01cdb1;
        }}
    </style>
</head>
<body>
    <div class="banner">
        <div class="job-title">
            Job Title: {{ job_title }}<br>
            Full Name: {{ full_name }}<br>
            Years of Experience: {{ years_of_experience }}<br>
        </div>
    </div>
    <div class="contact-strip">
        <div class="contact-info">
            <div>
                <span class="contact-icon">📞</span> {{ phone }}
            </div>
            <div>
                <span class="contact-icon">✉️</span> {{ email }}
            </div>
            <div>
                <span class="contact-icon">🌐</span> {{ website }}
            </div>
        </div>
    </div>
    <div class="section">
        <div class="section-title">Compétences techniques</div>
        <div class="section-content">
            {{ competences_techniques }}
        </div>
    </div>
    <div class="section">
        <div class="section-title">Formations</div>
        <div class="section-content">
            {{ formations }}
        </div>
    </div>
    <div class="section">
        <div class="section-title">Expériences professionnelles</div>
        <div class="section-content">
            <div class="company-name">{{ company_name }}</div>
            <div class="date-range">{{ date_range }}</div>
            <ul>
                <li class="tasks">{{ tasks }}</li>
                <li class="mission">{{ mission }}</li>
            </ul>
            <div class="tech-tools">{{ tech_tools }}</div>
        </div>
    </div>
</body>
</html>
"""
    try:
        response = openai_client.completions.create(
            model=insert_deployment,
            prompt=prompt,
            max_tokens=1500
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print(f"Error in generating completion: {e}")
        return None

def save_html_to_file(html_content, output_file):
    try:
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(html_content)
        return True
    except Exception as e:
        print(f"Error saving HTML output: {e}")
        return False

def convert_html_to_pdf(html_file, pdf_file):
    try:
        # Removed 'enable-local-file-access' from options
        options = {}
        pdfkit.from_file(html_file, pdf_file, configuration=config, options=options)
        return True
    except Exception as e:
        print(f"Error converting HTML to PDF: {e}")
        return False

def copy_image_to_output_dir(image_path, output_dir):
    dest_image_path = os.path.join(output_dir, os.path.basename(image_path))
    if os.path.abspath(image_path) == os.path.abspath(dest_image_path):
        print("Image already in the destination directory.")
        return True
    try:
        shutil.copy(image_path, dest_image_path)
        return True
    except Exception as e:
        print(f"Error copying image: {e}")
        return False

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://talentmatch.heptasys.com"}}, allow_headers=["Content-Type", "Authorization", "X-Requested-With"])

@app.route('/template', methods=['POST'])
@cross_origin()
def upload_template():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    file_path = os.path.join("uploads", file.filename)
    file.save(file_path)

    image_path = os.path.join("/app", "background.png")

    text = extract_text(file_path)
    if not text:
        return jsonify({"error": "Failed to extract text"}), 500

    structured_data = reformulate_text(text)
    if not structured_data:
        return jsonify({"error": "Failed to reformulate text"}), 500

    image_path = request.form.get('image_path', 'background.png')
    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)

    if copy_image_to_output_dir(image_path, output_dir):
        image_absolute_path = os.path.join(output_dir, os.path.basename(image_path))
        corrected_path = image_absolute_path.replace("\\", "/")
        image_url = f'file:///{corrected_path}'
        final_html = insert_text_into_template(structured_data, image_url)
        if not final_html:
            return jsonify({"error": "Failed to insert text into template"}), 500

        output_file = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(file.filename))[0]}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.html")
        if not save_html_to_file(final_html, output_file):
            return jsonify({"error": "Failed to save HTML output"}), 500

        pdf_file = f"{os.path.splitext(output_file)[0]}.pdf"
        if not convert_html_to_pdf(output_file, pdf_file):
            return jsonify({"error": "Failed to convert HTML to PDF"}), 500

        return send_file(pdf_file, as_attachment=True, download_name=os.path.basename(pdf_file), mimetype='application/pdf')
    else:
        return jsonify({"error": "Failed to copy the image"}), 500

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
