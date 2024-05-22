import os
import time
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import datetime
import pdfkit
from openai import AzureOpenAI
from tqdm import tqdm
import shutil
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from flask_cors import CORS
from flask_cors import cross_origin

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://talentmatch.heptasys.com"}}, allow_headers=["Content-Type", "Authorization", "X-Requested-With"])

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

# Ensure the correct path to wkhtmltopdf
path_to_wkhtmltopdf = '/usr/local/bin/wkhtmltopdf'
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
    prompt = f"take a deep breath,Extract from the following text these information in the form of a list: full name, job title, years of experience(based on the date range or ranges), phone, email, website, tech tools, tasks, mission or missions, date range or ranges, company name or names.\n\n{text}"
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
    prompt = f"""take a deep breath,Insert INTELLIGENTLY ONLY the following structured data into the HTML template that has variables for each section generate the exact same template with the structured data inserted,you find places for them,FOLLOW THE TEMPLATE:\n\nStructured Data:\n{structured_data}\n\nTemplate:
<!-- HTML template part skipped for brevity -->
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
        # Ensure wkhtmltopdf executable is specified
        config = pdfkit.configuration(wkhtmltopdf=path_to_wkhtmltopdf)
        options = {
            'enable-local-file-access': ''
        }
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


@app.route('/template', methods=['POST'])
@cross_origin()
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    file_path = os.path.join("uploads", file.filename)
    file.save(file_path)

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

        return send_file(pdf_file, as_attachment=True)
    else:
        return jsonify({"error": "Failed to copy the image"}), 500

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
