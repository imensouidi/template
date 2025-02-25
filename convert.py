import json
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
from openai import AzureOpenAI
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from flask import Flask, request, render_template, jsonify
import os
import logging
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from flask_cors import CORS
import tempfile
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration de l'application Flask
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://talent.heptasys.com", "http://localhost:4200"]}},
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"])
logging.basicConfig(level=logging.INFO)

# Configuration d'Azure Key Vault
key_vault_name = 'AI-vault-hepta'  # À adapter à votre Key Vault
key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)

# Récupération des secrets depuis le Key Vault
api_key = secret_client.get_secret('AZUREopenaiAPIkey').value
azure_endpoint = secret_client.get_secret('AZUREopenaiENDPOINT').value
connect_string = secret_client.get_secret('connectstr').value

# Configuration du client Azure OpenAI
azure_openai_client = AzureOpenAI(
    api_key=api_key,
    api_version="2024-02-15-preview",
    azure_endpoint=azure_endpoint
)

# Configuration d'Azure Blob Storage
blob_service_client = BlobServiceClient.from_connection_string(connect_string)
container_name = "converted"  # Nom du conteneur où on stocke les PDF générés

def get_account_key_from_connection_string(conn_str):
    """
    Extrait la clé de compte depuis la chaîne de connexion.
    """
    parts = conn_str.split(';')
    for part in parts:
        if part.strip().startswith("AccountKey="):
            return part.split("=", 1)[1]
    return None

_account_key = None
if hasattr(blob_service_client.credential, "account_key"):
    _account_key = blob_service_client.credential.account_key
else:
    _account_key = get_account_key_from_connection_string(connect_string)

def extract_text(file_path):
    """
    Extrait le texte d'un fichier PDF, DOCX ou Image
    sans reformater les dates.
    """
    try:
        if file_path.lower().endswith(".pdf"):
            with fitz.open(file_path) as doc:
                return " ".join(page.get_text() for page in doc)
        elif file_path.lower().endswith(".docx"):
            doc = Document(file_path)
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        else:
            # Supposons qu'il s'agit d'une image
            image = Image.open(file_path)
            return pytesseract.image_to_string(image)
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction du texte : {e}")
        return None

def extract_info_to_json(text):
    """
    Appelle Azure OpenAI pour extraire des informations structurées au format JSON.
    IMPORTANT :
    - Ne traduisez PAS le texte en anglais.
    - Conservez l'ordre exact des expériences.
    - Pour chaque entrée de "professional_experience", extrayez et restituez exactement
      les champs "date_range", "company_name" et "mission" (le poste) tels qu'ils apparaissent dans le CV.
      Par exemple, si le CV contient la ligne "Novembre2023  - Janvier2025    RAJA" suivie d'une ligne avec
      "Database Administrator (DBA MSSQL , POSTGRES )", alors "date_range" doit être "Novembre2023  - Janvier2025",
      "company_name" doit être "RAJA" et "mission" doit être "Database Administrator (DBA MSSQL , POSTGRES )".
    - Retournez uniquement du JSON valide (aucun texte supplémentaire).
    """
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
      "mission": "",
      "tasks": [
        ""
      ],
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
You are a helpful assistant that extracts specific information from a résumé (CV) written in French.
IMPORTANT:
- The text is in French. DO NOT translate it.
- Preserve the exact order of the professional experiences as they appear.
- For each entry in "professional_experience", extract exactly the following fields exactly as they appear in the CV:
  - "date_range": the date range (e.g., "Novembre2023  - Janvier2025")
  - "company_name": the company name (e.g., "RAJA")
  - "mission": the job title or position, which usually appears on the line immediately after the date and company line (e.g., "Database Administrator (DBA MSSQL , POSTGRES )")
- Return only valid JSON (no extra text or symbols).

Extract the following information from the text (in French):
{text}

Format the result as JSON according to the example below:
{json_format}

Do not include any extra symbols.
    """
    
    try:
        response = azure_openai_client.completions.create(
            model="IndexSelector",  # À adapter selon votre configuration
            prompt=prompt,
            max_tokens=3000,
            temperature=0
        )
        return response.choices[0].text.strip()
    except Exception as e:
        logging.error(f"Erreur lors de l'appel à l'API OpenAI : {e}")
        return None


def clean_and_save_json(raw_json_text, file_path):
    """
    Sauvegarde proprement le JSON dans un fichier.
    """
    try:
        clean_json_data = json.loads(raw_json_text)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_json_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Fichier JSON sauvegardé à {file_path}.")
    except json.JSONDecodeError as e:
        logging.error(f"Erreur de décodage JSON : {e}")

def generate_pdf_filename(json_data, original_filename):
    """
    Génère un nom de fichier PDF en conservant le nom d'entrée + '_output'.
    """
    base_name, _ = os.path.splitext(original_filename)
    return f"{base_name}_output.pdf"

def generate_pdf_from_json(json_data, output_file):
    """
    Génère un PDF à partir des données JSON en conservant l'ordre et le texte (en français)
    tels qu’ils figurent dans le JSON.
    """
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Ajout de styles personnalisés
    styles.add(ParagraphStyle(name='Center', alignment=1))
    styles.add(ParagraphStyle(name='Right', alignment=2))
    styles.add(ParagraphStyle(name='Section', fontSize=16, textColor=colors.turquoise, spaceAfter=12))
    styles.add(ParagraphStyle(name='Bold', parent=styles['Normal'], fontName='Helvetica-Bold'))
    
    def draw_banner(canvas_obj, doc_obj):
        try:
            banner_path = "Background.png"
            if os.path.exists(banner_path):
                banner_img = ImageReader(banner_path)
                banner_height = 2 * inch
                canvas_obj.drawImage(banner_img, 0, A4[1]-banner_height, width=A4[0], height=banner_height)
            else:
                logging.warning(f"Bannière introuvable : {banner_path}")
        except Exception as e:
            logging.error(f"Erreur lors du chargement de la bannière : {e}")
        canvas_obj.setFillColor(colors.white)
        
        job_title = json_data.get('job_title', '').replace('\n', ' ').strip() or "CV Title"
        years_experience = str(json_data.get('years_of_experience', '')).replace('\n', ' ').strip()
        canvas_obj.setFont("Helvetica-Bold", 20)
        text_y_position = A4[1]-0.75*inch
        job_title_width = canvas_obj.stringWidth(job_title, "Helvetica-Bold", 20)
        job_title_x = (A4[0]-job_title_width)/2
        canvas_obj.drawString(job_title_x, text_y_position, job_title)
        canvas_obj.setFont("Helvetica-Bold", 16)
        experience_text = "A.L : " + years_experience + " XP"
        experience_width = canvas_obj.stringWidth(experience_text, "Helvetica-Bold", 16)
        experience_x = (A4[0]-experience_width)/2
        canvas_obj.drawString(experience_x, text_y_position-40, experience_text)
        icon_y_position = A4[1]-inch-60
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(80, icon_y_position, "01 40 76 01 49")
        canvas_obj.drawString(260, icon_y_position, "heptasys@heptasys.com")
        canvas_obj.drawString(470, icon_y_position, "www.heptasys.com")
    
    # Espace pour la bannière
    story.append(Spacer(1,100))
    
    # --- Section Formation & Certifications ---
    story.append(Paragraph("Formation & Certifications", styles['Section']))
    for edu in json_data.get('education', []):
        degree = edu.get('degree', '').replace('\n', ' ')
        institution = edu.get('institution', '').replace('\n', ' ')
        year = str(edu.get('year_of_completion', ''))
        education_text = f"{degree} à {institution} ({year})"
        story.append(Paragraph(education_text, styles['Normal']))
    story.append(Spacer(1,12))
    if json_data.get('certifications'):
        for cert in json_data.get('certifications', []):
            cert_text = cert.get('name', '') if isinstance(cert, dict) else cert
            story.append(Paragraph(cert_text, styles['Normal']))
            story.append(Spacer(1,6))
    story.append(Spacer(1,12))
    
    # --- Section Compétences techniques ---
    story.append(Paragraph("Compétences techniques", styles['Section']))
    skills_section = json_data.get('skills', {})
    if isinstance(skills_section, dict) and skills_section:
        for category_key, skills in skills_section.items():
            category_title = category_key.replace('_', ' ').title() + " :"
            skills_text = ", ".join(skills)
            story.append(Paragraph(f"<b>{category_title}</b> {skills_text}", styles['Normal']))
            story.append(Spacer(1,6))
    else:
        technical_skills = ", ".join(json_data.get('technical_skills', []))
        story.append(Paragraph(technical_skills, styles['Normal']))
    story.append(Spacer(1,12))
    
    # --- Section Expériences professionnelles ---
    story.append(Paragraph("Expériences professionnelles", styles['Section']))
    for exp in json_data.get('professional_experience', []):
        date_range = exp.get('date_range', '').strip() or "Date non renseignée"
        company_name = exp.get('company_name', '').replace('\n', ' ').strip()
        mission = exp.get('mission', '').replace('\n', ' ').strip() or "Poste non renseigné"
        
        table_data = [
            [
                Paragraph(f"<b>{date_range}</b>", styles['Normal']),
                Paragraph(f"<b>{company_name}</b>", styles['Normal'])
            ]
        ]
        table = Table(table_data, colWidths=[3.0*inch, 3.0*inch])
        table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'RIGHT')
        ]))
        story.append(table)
        story.append(Paragraph(mission, styles['Bold']))
        if exp.get('tasks'):
            story.append(Paragraph("Tâches :", styles['Bold']))
            for task in exp.get('tasks'):
                story.append(Paragraph("• " + task.replace('\n', ' '), styles['Normal']))
        if exp.get('tech_tools'):
            tech_tools = ", ".join(exp.get('tech_tools', []))
            story.append(Paragraph("Outils : " + tech_tools, styles['Normal']))
        story.append(Spacer(1,12))
    
    doc.build(story, onFirstPage=draw_banner)

def generate_sas_token(blob_name):
    try:
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=_account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        return blob_url
    except Exception as e:
        logging.error(f"Erreur lors de la génération du SAS token : {e}")
        return None

@app.route('/generate-sas-token', methods=['POST'])
def generate_sas_token_route():
    data = request.json
    blob_name = data.get('blob_name')
    if not blob_name:
        return jsonify({"error": "Le nom du blob est requis"}), 400
    sas_url = generate_sas_token(blob_name)
    if sas_url:
        return jsonify({"sas_url": sas_url}), 200
    else:
        return jsonify({"error": "Échec de la génération du SAS token"}), 500

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_blob_storage(file_path, blob_name):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        logging.info(f"Fichier {blob_name} uploadé vers Azure Blob Storage.")
    except Exception as e:
        logging.error(f"Erreur lors de l'upload vers Blob Storage : {e}")

@app.route('/template', methods=['POST'])
def upload_file():
    logging.info("Requête reçue sur /template")
    if 'file' not in request.files:
        logging.error("Aucun fichier trouvé dans la requête")
        return jsonify({"error": "Aucun fichier trouvé dans la requête"}), 400

    file = request.files['file']
    if file.filename == '':
        logging.error("Aucun fichier sélectionné")
        return jsonify({"error": "Aucun fichier sélectionné"}), 400

    if file and allowed_file(file.filename):
        filename = file.filename
        file_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(file_path)
        logging.info(f"Fichier sauvegardé à {file_path}")

        extracted_text = extract_text(file_path)
        if not extracted_text:
            logging.error("Aucun texte extrait du fichier")
            return jsonify({"error": "Échec de l'extraction du texte"}), 500
        logging.info("Texte extrait du fichier")

        json_info = extract_info_to_json(extracted_text)
        if not json_info:
            logging.error("Échec de l'extraction des informations structurées")
            return jsonify({"error": "Échec de l'extraction des informations structurées"}), 500
        logging.info("Informations extraites au format JSON")

        json_file_path = os.path.join(tempfile.gettempdir(), 'extracted_info.json')
        clean_and_save_json(json_info, json_file_path)
        if not os.path.exists(json_file_path):
            logging.error(f"Fichier JSON non trouvé à {json_file_path}")
            return jsonify({"error": "Échec de la sauvegarde du fichier JSON"}), 500

        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        logging.info("Données JSON chargées : %s", json_data)

        pdf_file_name = generate_pdf_filename(json_data, filename)
        pdf_file_path = os.path.join(tempfile.gettempdir(), pdf_file_name)

        generate_pdf_from_json(json_data, pdf_file_path)
        logging.info(f"PDF généré à {pdf_file_path}")

        upload_to_blob_storage(pdf_file_path, pdf_file_name)
        logging.info(f"PDF uploadé vers Blob Storage sous le nom {pdf_file_name}")

        sas_url = generate_sas_token(pdf_file_name)
        if sas_url:
            logging.info(f"SAS URL généré : {sas_url}")
            return jsonify({"sas_url": sas_url}), 200
        else:
            logging.error("Échec de la génération du SAS token")
            return jsonify({"error": "Échec de la génération du SAS token"}), 500
    else:
        logging.error("Fichier non valide ou extension non autorisée")
        return jsonify({"error": "Fichier non valide ou extension non autorisée"}), 400

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
