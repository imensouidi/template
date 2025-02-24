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
            # Suppose qu'il s'agit d'une image
            image = Image.open(file_path)
            return pytesseract.image_to_string(image)
    except Exception as e:
        logging.error(f"Error extracting text: {e}")
        return None


def extract_info_to_json(text):
    """
    Appelle Azure OpenAI pour extraire des informations structurées
    au format JSON. IMPORTANT: On exige de NE PAS traduire le texte
    et de préserver l'ordre exact d'apparition des expériences.
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
 You are a helpful assistant that extracts specific information from a résumé (CV) written in French.
 IMPORTANT:
 - The text is in French. DO NOT translate any French text into English.
 - Preserve the exact textual order of the professional experiences as they appear in the CV (do not reorder).
 - Keep date ranges exactly as they appear (do not reformat).
 - Return only valid JSON (no extra text or symbols).

 Extract the following information from the text (in French):
 {text}

 Format the result as JSON according to the example below:
 {json_format}
 Do not include any extra symbols; provide only valid JSON output.
    """

    try:
        response = azure_openai_client.completions.create(
            model="IndexSelector",  # À adapter selon votre config
            prompt=prompt,
            max_tokens=3000,
            temperature=0  # pour limiter la créativité et garder le texte au plus proche
        )
        return response.choices[0].text.strip()
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None


def clean_and_save_json(raw_json_text, file_path):
    """
    Sauvegarde proprement le JSON dans un fichier.
    """
    try:
        clean_json_data = json.loads(raw_json_text)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_json_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Clean JSON file saved successfully at {file_path}.")
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")


def generate_pdf_filename(json_data, original_filename):
    """
    Génère un nom de fichier PDF en conservant le nom d'entrée + '_output'.
    """
    base_name, _ = os.path.splitext(original_filename)
    return f"{base_name}_output.pdf"


def generate_pdf_from_json(json_data, output_file):
    """
    Génère un PDF à partir des données JSON en conservant l'ordre
    et le texte (en français) tels qu’ils figurent dans le JSON.
    """
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Ajout de quelques styles personnalisés
    styles.add(ParagraphStyle(name='Center', alignment=1))
    styles.add(ParagraphStyle(name='Right', alignment=2))
    styles.add(ParagraphStyle(name='Section', fontSize=16, textColor=colors.turquoise, spaceAfter=12))
    styles.add(ParagraphStyle(name='Bold', parent=styles['Normal'], fontName='Helvetica-Bold'))

    def draw_banner(canvas_obj, doc_obj):
        """
        Dessine la bannière d'en-tête (exemple).
        """
        try:
            # Remplacez "Background.png" par l'image de votre bannière si nécessaire
            banner_img = ImageReader("Background.png")
            banner_height = 2 * inch
            canvas_obj.drawImage(banner_img, 0, A4[1] - banner_height, width=A4[0], height=banner_height)
        except Exception as e:
            logging.error(f"Error loading banner image: {e}")
        canvas_obj.setFillColor(colors.white)

        job_title = json_data.get('job_title', '').replace('\n', ' ').strip() or "CV Title"
        years_experience = str(json_data.get('years_of_experience', '')).replace('\n', ' ').strip()

        # Titre
        canvas_obj.setFont("Helvetica-Bold", 20)
        text_y_position = A4[1] - 0.75 * inch
        job_title_width = canvas_obj.stringWidth(job_title, "Helvetica-Bold", 20)
        job_title_x = (A4[0] - job_title_width) / 2
        canvas_obj.drawString(job_title_x, text_y_position, job_title)

        # Années d'expérience
        canvas_obj.setFont("Helvetica-Bold", 16)
        experience_text = "A.L : " + years_experience + " XP"
        experience_width = canvas_obj.stringWidth(experience_text, "Helvetica-Bold", 16)
        experience_x = (A4[0] - experience_width) / 2
        canvas_obj.drawString(experience_x, text_y_position - 40, experience_text)

        # Exemple d'infos de contact en dur
        icon_y_position = A4[1] - inch - 60
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(80, icon_y_position, "01 40 76 01 49")
        canvas_obj.drawString(260, icon_y_position, "heptasys@heptasys.com")
        website = "www.heptasys.com"
        canvas_obj.drawString(470, icon_y_position, website)

    # Laisser un espace pour ne pas empiéter sur la bannière
    story.append(Spacer(1, 100))

    # --- Compétences techniques ---
    story.append(Paragraph("Compétences techniques", styles['Section']))
    skills_section = json_data.get('skills', {})
    if isinstance(skills_section, dict) and skills_section:
        for category_key, skills in skills_section.items():
            category_title = category_key.replace('_', ' ').title() + " :"
            skills_text = ", ".join(skills)
            story.append(Paragraph(f"<b>{category_title}</b> {skills_text}", styles['Normal']))
            story.append(Spacer(1, 6))
    else:
        # Si pas de structure "skills", on regarde "technical_skills"
        technical_skills = ", ".join(json_data.get('technical_skills', []))
        story.append(Paragraph(technical_skills, styles['Normal']))
    story.append(Spacer(1, 12))

    # --- Formation ---
    story.append(Paragraph("Formation", styles['Section']))
    for edu in json_data.get('education', []):
        degree = edu.get('degree', '').replace('\n', ' ')
        institution = edu.get('institution', '').replace('\n', ' ')
        year = str(edu.get('year_of_completion', ''))
        education_text = f"{degree} à {institution} ({year})"
        story.append(Paragraph(education_text, styles['Normal']))
    story.append(Spacer(1, 12))

    # --- Expériences professionnelles ---
    story.append(Paragraph("Expériences professionnelles", styles['Section']))
    professional_experiences = json_data.get('professional_experience', [])

    # On boucle dans l'ordre d'apparition du JSON (aucun tri).
    for exp in professional_experiences:
        date_range = exp.get('date_range', '')
        company_name = exp.get('company_name', '').replace('\n', ' ')
        job_position = exp.get('mission', '').replace('\n', ' ')

        # Tableau pour aligner la date à gauche et l'entreprise à droite
        table_data = [
            [
                Paragraph(f"<b>{date_range}</b>", styles['Normal']),
                Paragraph(f"<b>{company_name}</b>", styles['Normal'])
            ]
        ]
        table = Table(table_data, colWidths=[3.0 * inch, 3.0 * inch])
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT')
        ]))
        story.append(table)

        # Poste (mission)
        if job_position:
            story.append(Paragraph(job_position, styles['Bold']))

        # Tâches
        tasks = exp.get('tasks', [])
        if tasks:
            story.append(Paragraph("Tâches :", styles['Bold']))
            for task in tasks:
                story.append(Paragraph("• " + task.replace('\n', ' '), styles['Normal']))

        # Outils
        tech_tools = ", ".join(exp.get('tech_tools', []))
        if tech_tools:
            story.append(Paragraph("Outils : " + tech_tools, styles['Normal']))

        story.append(Spacer(1, 12))

    # --- Certifications ---
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

    # Construction du PDF
    doc.build(story, onFirstPage=draw_banner)


def generate_sas_token(blob_name):
    """
    Génère un SAS token pour la lecture du blob (valable 10 minutes).
    """
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


def allowed_file(filename):
    """
    Vérifie que l'extension du fichier est autorisée (PDF ou DOCX).
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'docx'}


def upload_to_blob_storage(file_path, blob_name):
    """
    Upload du fichier généré vers Azure Blob Storage.
    """
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
    logging.info(f"File {blob_name} uploaded to Azure Blob Storage.")


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

        # 1) Extraction du texte
        extracted_text = extract_text(file_path)
        if extracted_text:
            logging.info("Text extracted from file")

            # 2) Appel à OpenAI pour extraire le JSON
            json_info = extract_info_to_json(extracted_text)
            if json_info:
                logging.info("Information extracted to JSON")

                # 3) Sauvegarde du JSON
                json_file_path = os.path.join(tempfile.gettempdir(), 'extracted_info.json')
                clean_and_save_json(json_info, json_file_path)
                if not os.path.exists(json_file_path):
                    logging.error(f"JSON file not found at {json_file_path}")
                    return "Failed to save JSON file."

                with open(json_file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                logging.info("JSON Data: %s", json_data)

                # 4) Génération du nom de fichier PDF
                pdf_file_name = generate_pdf_filename(json_data, filename)
                pdf_file_path = os.path.join(tempfile.gettempdir(), pdf_file_name)

                # 5) Génération du PDF
                generate_pdf_from_json(json_data, pdf_file_path)
                logging.info(f"PDF generated at {pdf_file_path}")

                # 6) Upload vers Blob Storage
                upload_to_blob_storage(pdf_file_path, pdf_file_name)
                logging.info(f"PDF uploaded to blob storage as {pdf_file_name}")

                # 7) Génération du SAS token
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

    # Si pas de fichier valide, on renvoie la page d'upload par défaut
    return render_template('upload.html')


if __name__ == "__main__":
    # Lancez le serveur Flask
    app.run(host='0.0.0.0', port=5001, debug=True)
