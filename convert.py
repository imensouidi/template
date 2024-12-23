import json
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
from openai import AzureOpenAI
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from flask import Flask, request, render_template, redirect, url_for
import os
import logging
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, generate_blob_sas, BlobSasPermissions
from flask_cors import CORS
import tempfile
from dotenv import load_dotenv  # Import python-dotenv
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

# Flask app setup
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://talent.heptasys.com", "http://localhost:4200"]}}, allow_headers=["Content-Type", "Authorization", "X-Requested-With"])
logging.basicConfig(level=logging.INFO)

# Azure Key Vault setup
key_vault_name = 'AI-vault-hepta'
key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)

# OpenAI client setup using Azure
api_key = secret_client.get_secret('AZUREopenaiAPIkey').value
azure_endpoint = secret_client.get_secret('AZUREopenaiENDPOINT').value
azure_openai_client = AzureOpenAI(api_key=api_key, api_version="2024-02-15-preview", azure_endpoint=azure_endpoint)

# Azure Blob Storage setup
connect_string = secret_client.get_secret('connectstr').value
blob_service_client = BlobServiceClient.from_connection_string(connect_string)
container_name = "converted"

# OS Section
# Adding an OS section to handle file paths and environment variables
# Ensure that the necessary environment variables are set in the .env file

# Accessing environment variables from .env
#api_key = os.getenv('AZURE_OPENAI_API_KEY')
#azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
#connect_string = os.getenv('AZURE_BLOB_STORAGE_CONNECTION_STRING')

# Initialize Azure OpenAI client
#azure_openai_client = AzureOpenAI(api_key=api_key, api_version="2024-02-15-preview", azure_endpoint=azure_endpoint)

# Initialize Blob Storage client
#blob_service_client = BlobServiceClient.from_connection_string(connect_string)
#container_name = "converted"

# Extract text from file
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
        logging.error(f"Error extracting text: {e}")
        return None

def extract_info_to_json(text):
    Json_format = """
    {
      "job_title": "",
      "full_name": "",
      "years_of_experience": "",
      "contact_information": {
        "phone": "",
        "email": "",
        "website": ""
      },
      "competences_techniques": [
        ""
      ],
      "formations": [
        {
          "degree": "",
          "institution": "",
          "year_of_completion": ""
        }
      ],
      "experiences_professionnelles": [
        {
          "company_name": "",
          "date_range": "",
          "tasks": [
            ""
          ],
          "mission": "",
          "tech_tools": [
            ""
          ]
        }
      ],
      "skills": {
        "soft_skills": [
            ""
        ],
        "programming_languages": [
            ""
        ],
        "frameworks_libraries": [
            ""
        ],

      },
      "certifications": [
        ""
      ],
    }
    """
    prompt = f"""
    You are a helpful assistant that extracts specific information from a text and formats it into JSON.
    Extract the following specific information from the text   {text} and put it into JSON FORMAT like this example:
    {Json_format}
    IMPORTANT NOTE: Don't put other symbols like / or /n just structure the output to be in a good JSON FILE. Give me the right output of json because I will save the output directly into a JSON file AND extract the text word for word .
    """
    try:
        response = azure_openai_client.completions.create(
            model="IndexSelector",
            prompt=prompt,
            max_tokens=3000
        )
        return response.choices[0].text.strip()
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None

def clean_and_save_json(raw_json_text, file_path):
    try:
        clean_json_data = json.loads(raw_json_text)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_json_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Clean JSON file saved successfully at {file_path}.")
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")

def generate_pdf_from_json(json_data, output_file):
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    styles.add(ParagraphStyle(name='Center', alignment=1))
    styles.add(ParagraphStyle(name='Right', alignment=2))
    styles.add(ParagraphStyle(name='Section', fontSize=16, textColor=colors.turquoise, spaceAfter=12))
    styles.add(ParagraphStyle(name='Bold', parent=styles['Normal'], fontName='Helvetica-Bold'))

    def draw_banner(canvas, doc):
        banner_img = ImageReader("Background.png")
        banner_height = 2 * inch
        canvas.drawImage(banner_img, 0, A4[1] - banner_height, width=A4[0], height=banner_height)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 16)
        
        # Move job title, full name, and experience section up a little bit
        text_y_position = A4[1] - 0.75 * inch
        job_title_x = (A4[0] - canvas.stringWidth("Job Title: " + json_data.get('job_title', '').replace('\n', ' '))) / 2
        full_name_x = (A4[0] - canvas.stringWidth("Full Name: " + json_data.get('full_name', '').replace('\n', ' '))) / 2
        experience_x = (A4[0] - canvas.stringWidth("Years of Experience: " + str(json_data.get('years_of_experience', '')).replace('\n', ' '))) / 2
        canvas.drawString(job_title_x, text_y_position, "Job Title: " + json_data.get('job_title', '').replace('\n', ' '))
        canvas.drawString(full_name_x, text_y_position - 20, "Full Name: " + json_data.get('full_name', '').replace('\n', ' '))
        canvas.drawString(experience_x, text_y_position - 40, "Years of Experience: " + str(json_data.get('years_of_experience', '')).replace('\n', ' '))
        
        # Move the contact information up a bit
        icon_y_position = A4[1] - inch - 60
        contact_info = json_data['contact_information']
        
        canvas.setFont("Helvetica", 8)
        canvas.drawString(80, icon_y_position, contact_info.get('phone', '').replace('\n', ' '))
        canvas.drawString(260, icon_y_position, contact_info.get('email', '').replace('\n', ' '))
        
        website = contact_info.get('website', '').replace('\n', ' ')
        if len(website) > 30:
            website_lines = [website[:30], website[30:]]
            canvas.drawString(470, icon_y_position, website_lines[0])
            canvas.drawString(470, icon_y_position - 10, website_lines[1])
        else:
            canvas.drawString(470, icon_y_position, website)

    doc.build(story, onFirstPage=draw_banner)

    # Contact Information Section
   
    story.append(Spacer(1, 66))
    
    story.append(Paragraph("Compétences techniques", styles['Section']))
    skills = ", ".join(json_data.get('competences_techniques', []))
    story.append(Paragraph(skills, styles['Normal']))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Formations", styles['Section']))
    for formation in json_data.get('formations', []):
        # Preprocess the values to replace newline characters
        degree = formation.get('degree', '').replace('\n', ' ')
        institution = formation.get('institution', '').replace('\n', ' ')
        year_of_completion = str(formation.get('year_of_completion', ''))

        # Use the preprocessed values in the f-string
        formation_text = f"{degree} at {institution} ({year_of_completion})"
        story.append(Paragraph(formation_text, styles['Normal']))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Expériences professionnelles", styles['Section']))
    for exp in json_data.get('experiences_professionnelles', []):
        story.append(Paragraph(exp.get('company_name', '').replace('\n', ' '), styles['Heading3']))
        story.append(Paragraph(exp.get('date_range', '').replace('\n', ' '), styles['Italic']))
        story.append(Paragraph("Tasks:", styles['Bold']))
        for task in exp.get('tasks', []):
            story.append(Paragraph("• " + task.replace('\n', ' '), styles['Normal']))
        story.append(Paragraph("Mission: " + exp.get('mission', '').replace('\n', ' '), styles['Normal']))
        story.append(Paragraph("Technologies: " + ', '.join(exp.get('tech_tools', [])).replace('\n', ' '), styles['Normal']))
        story.append(Spacer(1, 12))

    # Dynamic Skills Section
    skills_section = json_data.get('skills', {})
    if isinstance(skills_section, dict):
        story.append(Paragraph("Skills", styles['Section']))
        # Soft Skills
        if skills_section.get('soft_skills'):
            story.append(Paragraph("Soft Skills:", styles['Bold']))
            story.append(Paragraph(", ".join(skills_section.get('soft_skills', [])), styles['Normal']))
        # Programming Languages
        if skills_section.get('programming_languages'):
            story.append(Paragraph("Programming Languages:", styles['Bold']))
            story.append(Paragraph(", ".join(skills_section.get('programming_languages', [])), styles['Normal']))
        # Frameworks & Libraries
        if skills_section.get('frameworks_libraries'):
            story.append(Paragraph("Frameworks & Libraries:", styles['Bold']))
            story.append(Paragraph(", ".join(skills_section.get('frameworks_libraries', [])), styles['Normal']))
        # IDEs & Development Tools
        if skills_section.get('ides_development_tools'):
            story.append(Paragraph("IDEs & Development Tools:", styles['Bold']))
            story.append(Paragraph(", ".join(skills_section.get('ides_development_tools', [])), styles['Normal']))
        # Certifications
        if json_data.get('certifications'):
            certifications = []
            for cert in json_data.get('certifications', []):
                if isinstance(cert, dict):
                    # Extract the relevant string value from the dictionary
                    cert_name = cert.get('name', '')
                    certifications.append(cert_name)
                elif isinstance(cert, str):
                    certifications.append(cert)
            story.append(Paragraph("Certifications", styles['Section']))
            story.append(Paragraph(", ".join(certifications), styles['Normal']))

    doc.build(story)

def generate_sas_token(blob_name):
    try:
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=1)  # Change expiry to 1 minute
        )
        blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        return blob_url
    except Exception as e:
        logging.error(f"Error generating SAS token: {e}")
        return None

@app.route('/generate-sas-token', methods=['POST'])
def generate_sas_token_route():
    data = request.json
    blob_name = data.get('blob_name')
    if not blob_name:
        return {"error": "Blob name is required"}, 400
    sas_url = generate_sas_token(blob_name)
    if sas_url:
        return {"sas_url": sas_url}, 200
    else:
        return {"error": "Failed to generate SAS token"}, 500

@app.route('/template', methods=['POST'])
def upload_file():
    logging.info("Received a request at /template")
    if 'file' not in request.files:
        logging.error("No file part in the request")
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        logging.error("No selected file")
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = file.filename
        file_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(file_path)
        logging.info(f"File saved to {file_path}")
        extracted_text = extract_text(file_path)
        if extracted_text:
            logging.info("Text extracted from file")
            json_info = extract_info_to_json(extracted_text)
            if json_info:
                logging.info("Information extracted to JSON")
                json_file_path = os.path.join(tempfile.gettempdir(), 'extracted_info.json')
                clean_and_save_json(json_info, json_file_path)
                if not os.path.exists(json_file_path):
                    logging.error(f"JSON file not found at {json_file_path}")
                    return "Failed to save JSON file."
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                logging.info("JSON Data: %s", json_data)  # Debugging statement
                # Generate the PDF file name based on the uploaded file name
                base_name, _ = os.path.splitext(filename)
                pdf_file_name = f"{base_name}_output.pdf"
                pdf_file_path = os.path.join(tempfile.gettempdir(), pdf_file_name)
                generate_pdf_from_json(json_data, pdf_file_path)
                logging.info(f"PDF generated at {pdf_file_path}")
                upload_to_blob_storage(pdf_file_path, pdf_file_name)
                logging.info(f"PDF uploaded to blob storage as {pdf_file_name}")
                sas_url = generate_sas_token(pdf_file_name)
                if sas_url:
                    logging.info(f"SAS URL generated: {sas_url}")
                    return {"sas_url": sas_url}, 200
                else:
                    logging.error("Failed to generate SAS token")
                    return {"error": "Failed to generate SAS token"}, 500
            else:
                logging.error("Failed to extract structured information")
                return "Failed to extract structured information."
        else:
            logging.error("No text extracted from the file")
            return "No text extracted from the file."
    return render_template('upload.html')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'docx'}

def upload_to_blob_storage(file_path, blob_name):
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
    logging.info(f"File {blob_name} uploaded to Azure Blob Storage.")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
