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
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from flask import Flask, request, render_template, redirect
import os
import logging
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from flask_cors import CORS
import tempfile
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration de l'application Flask
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://talent.heptasys.com", "http://localhost:4200"]}},
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"])
logging.basicConfig(level=logging.INFO)

# Configuration d'Azure Key Vault
key_vault_name = 'AI-vault-hepta'
key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)

# Configuration du client Azure OpenAI
api_key = secret_client.get_secret('AZUREopenaiAPIkey').value
azure_endpoint = secret_client.get_secret('AZUREopenaiENDPOINT').value
azure_openai_client = AzureOpenAI(api_key=api_key, api_version="2024-02-15-preview", azure_endpoint=azure_endpoint)

# Configuration d'Azure Blob Storage
connect_string = secret_client.get_secret('connectstr').value
blob_service_client = BlobServiceClient.from_connection_string(connect_string)
container_name = "converted"

# Fonction pour extraire le texte d'un fichier (PDF, DOCX ou image)
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

# Fonction pour extraire des informations structurées au format JSON via Azure OpenAI
def extract_info_to_json(text):
    json_format = """
{
  "job_title": "",
  "full_name": "",
  "years_of_experience": "",
  "contact_information": {
    "phone": "",
    "email": "",
    "website": ""
  },
  "technical_skills": [
    ""
  ],
  "education": [
    {
      "degree": "",
      "institution": "",
      "year_of_completion": ""
    }
  ],
  "professional_experience": [
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
    "ides_development_tools": [
      ""
    ]
  },
  "certifications": [
    ""
  ]
}
    """
    prompt = f"""
You are a helpful assistant that extracts specific information from a text and formats it into JSON.
Extract the following information from the text: {text}
and format it as JSON according to the example below:
{json_format}
IMPORTANT: Do not include any extra symbols; provide only a valid JSON output.
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

# Sauvegarde du JSON extrait dans un fichier
def clean_and_save_json(raw_json_text, file_path):
    try:
        clean_json_data = json.loads(raw_json_text)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_json_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Clean JSON file saved successfully at {file_path}.")
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")

# Fonction pour générer dynamiquement le nom du PDF à partir du JSON
def generate_pdf_filename(json_data, original_filename):
    full_name = json_data.get('full_name', '').strip().replace(' ', '_')
    job_title = json_data.get('job_title', '').strip().replace(' ', '_')
    # Si on a les informations, on utilise le format souhaité
    if full_name and job_title:
        return f"CV_{full_name}_{job_title}_Heptasy.pdf"
    # Sinon, on revient à la méthode basée sur le nom original
    base_name, _ = os.path.splitext(original_filename)
    return f"{base_name}_output.pdf"

# Génération d'un PDF à partir des données JSON
def generate_pdf_from_json(json_data, output_file):
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    styles.add(ParagraphStyle(name='Center', alignment=1))
    styles.add(ParagraphStyle(name='Right', alignment=2))
    styles.add(ParagraphStyle(name='Section', fontSize=16, textColor=colors.turquoise, spaceAfter=12))
    styles.add(ParagraphStyle(name='Bold', parent=styles['Normal'], fontName='Helvetica-Bold'))
    
    # Bannière d'en-tête personnalisée (titre, expérience et infos de contact)
    def draw_banner(canvas_obj, doc_obj):
        try:
            banner_img = ImageReader("Background.png")
            banner_height = 2 * inch
            canvas_obj.drawImage(banner_img, 0, A4[1] - banner_height, width=A4[0], height=banner_height)
        except Exception as e:
            logging.error(f"Error loading banner image: {e}")
        canvas_obj.setFillColor(colors.white)
        job_title = json_data.get('job_title', '').replace('\n', ' ').strip() or "CV Title"
        years_experience = str(json_data.get('years_of_experience', '')).replace('\n', ' ').strip()
        canvas_obj.setFont("Helvetica-Bold", 20)
        text_y_position = A4[1] - 0.75 * inch
        job_title_width = canvas_obj.stringWidth(job_title, "Helvetica-Bold", 20)
        job_title_x = (A4[0] - job_title_width) / 2
        canvas_obj.drawString(job_title_x, text_y_position, job_title)
        canvas_obj.setFont("Helvetica-Bold", 16)
        experience_text = "A.L : " + years_experience + " XP"
        experience_width = canvas_obj.stringWidth(experience_text, "Helvetica-Bold", 16)
        experience_x = (A4[0] - experience_width) / 2
        canvas_obj.drawString(experience_x, text_y_position - 40, experience_text)
        icon_y_position = A4[1] - inch - 60
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(80, icon_y_position, "01 40 76 01 49")
        canvas_obj.drawString(260, icon_y_position, "heptasys@heptasys.com")
        website = "www.heptasys.com"
        canvas_obj.drawString(470, icon_y_position, website)
    
    # Ajouter un espace pour éviter la superposition avec la bannière
    story.append(Spacer(1, 100))
    
    # Affichage des compétences techniques par catégorie
    story.append(Paragraph("Compétences techniques", styles['Section']))
    skills_section = json_data.get('skills', {})
    if isinstance(skills_section, dict) and skills_section:
        for category_key, skills in skills_section.items():
            category_title = category_key.replace('_', ' ').title() + " :"
            story.append(Paragraph(category_title, styles['Bold']))
            for skill in skills:
                story.append(Paragraph(f"• {skill}", styles['Normal']))
            story.append(Spacer(1, 6))
    else:
        technical_skills = ", ".join(json_data.get('technical_skills', []))
        story.append(Paragraph(technical_skills, styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Section Éducation
    story.append(Paragraph("Formation", styles['Section']))
    for edu in json_data.get('education', []):
        degree = edu.get('degree', '').replace('\n', ' ')
        institution = edu.get('institution', '').replace('\n', ' ')
        year = str(edu.get('year_of_completion', ''))
        education_text = f"{degree} à {institution} ({year})"
        story.append(Paragraph(education_text, styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Section Expériences professionnelles
    story.append(Paragraph("Expériences professionnelles", styles['Section']))
    for exp in json_data.get('professional_experience', []):
        company_name = exp.get('company_name', '').replace('\n', ' ')
        if company_name:
            story.append(Paragraph(company_name, styles['Heading3']))
        date_range = exp.get('date_range', '').replace('\n', ' ')
        if date_range:
            story.append(Paragraph(date_range, styles['Italic']))
        story.append(Paragraph("Tâches :", styles['Bold']))
        for task in exp.get('tasks', []):
            story.append(Paragraph("• " + task.replace('\n', ' '), styles['Normal']))
        mission = exp.get('mission', '').replace('\n', ' ')
        if mission:
            story.append(Paragraph("Mission : " + mission, styles['Normal']))
        tech_tools = ", ".join(exp.get('tech_tools', []))
        if tech_tools:
            story.append(Paragraph("Outils : " + tech_tools, styles['Normal']))
        story.append(Spacer(1, 12))
    
    # Section Certifications (une certification par ligne)
    if json_data.get('certifications'):
        story.append(Paragraph("Certifications", styles['Section']))
        certifications = json_data.get('certifications', [])
        for cert in certifications:
            if isinstance(cert, dict):
                cert_text = cert.get('name', '')
            else:
                cert_text = cert
            story.append(Paragraph(cert_text, styles['Normal']))
            story.append(Spacer(1, 6))
    
    doc.build(story, onFirstPage=draw_banner)

# Générer un SAS token pour l'upload vers Blob Storage
def generate_sas_token(blob_name):
    try:
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=10)
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

# Vérification de l'extension du fichier
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'docx'}

# Upload du fichier généré vers Azure Blob Storage
def upload_to_blob_storage(file_path, blob_name):
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
    logging.info(f"File {blob_name} uploaded to Azure Blob Storage.")

# Route pour l'upload du fichier et le traitement du CV
@app.route('/template', methods=['POST'])
def upload_file():
    logging.info("Received a request at /template")
    if 'file' not in request.files:
        logging.error("No file part in the request")
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        logging.error("No file selected")
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
                logging.info("JSON Data: %s", json_data)
                # Génération dynamique du nom du PDF
                pdf_file_name = generate_pdf_filename(json_data, filename)
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
