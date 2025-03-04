import json
import re
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
from reportlab.lib.units import inch, cm
from reportlab.lib.utils import ImageReader
from flask import Flask, request, jsonify
import os
import logging
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from flask_cors import CORS
import tempfile
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from pdf2docx import Converter
from docx.shared import Inches
from docx.shared import Pt

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

api_key = secret_client.get_secret('AZUREopenaiAPIkey').value
azure_endpoint = secret_client.get_secret('AZUREopenaiENDPOINT').value
connect_string = secret_client.get_secret('connectstr').value

azure_openai_client = AzureOpenAI(
    api_key=api_key,
    api_version="2024-02-15-preview",
    azure_endpoint=azure_endpoint
)

blob_service_client = BlobServiceClient.from_connection_string(connect_string)
container_name = "converted"

def get_account_key_from_connection_string(conn_str):
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
        logging.error(f"Erreur lors de l'extraction du texte : {e}")
        return None

def extract_certifications(text):
    """
    Extrait la section "CERTIFICATION" du CV en récupérant le texte situé
    entre "CERTIFICATION" et le prochain titre (par ex. "CENTRES D’INTÉRÊT", "COMPÉTENCES" ou "EXPÉRIENCES PROFESSIONNELLES").
    Retourne une liste de certifications, une par ligne.
    """
    pattern = r"CERTIFICATION\s*(.*?)\s*(CENTRES\s*D’INTÉRÊT|COMPÉTENCES|EXPÉRIENCES\s+PROFESSIONNELLES|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        cert_text = match.group(1).strip()
        certs = [line.strip() for line in cert_text.splitlines() if line.strip()]
        return certs
    return []

def override_certifications_with_regex(text, json_data):
    certs = extract_certifications(text)
    if certs:
        json_data["certifications"] = certs
    return json_data

def extract_info_to_json(text):
    # Le JSON attendu inclut "skills" et "certifications"
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
      "tasks": [""],
      "tech_tools": [""]
    }
  ],
  "skills": [],
  "certifications": []
}
    """
    
    prompt = f"""
You are a helpful assistant that extracts specific information from a résumé (CV) written in French.
IMPORTANT:
- The text is in French. DO NOT translate it.
- Extract the technical skills information from the CV and return it in the "skills" field.
  If the skills are organized in categories, return a dictionary; if not, return a list of skills (each as a string).
- Extract the certifications from the CV and return them in the "certifications" field as a list of strings.
- Preserve the exact order of the professional experiences as they appear.
- For each entry in "professional_experience", extract exactly the following fields as they appear in the CV:
  "date_range", "company_name", and "mission". IMPORTANT: For "mission", extract only the job title – i.e. the first line immediately following the date range and company name – and do not include any additional descriptive text.
- Return only valid JSON (no extra text or symbols).

Extract the following information from the text (in French):
{text}

Format the result as JSON according to the example below:
{json_format}

Do not include any extra symbols.
    """
    try:
        response = azure_openai_client.completions.create(
            model="IndexSelector",
            prompt=prompt,
            max_tokens=3000,
            temperature=0
        )
        return response.choices[0].text.strip()
    except Exception as e:
        logging.error(f"Erreur lors de l'appel à l'API OpenAI : {e}")
        return None

def clean_and_save_json(raw_json_text, file_path):
    try:
        clean_json_data = json.loads(raw_json_text)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_json_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Fichier JSON sauvegardé à {file_path}.")
    except json.JSONDecodeError as e:
        logging.error(f"Erreur de décodage JSON : {e}")

def generate_pdf_filename(json_data, original_filename):
    base_name, _ = os.path.splitext(original_filename)
    return f"{base_name}_output.pdf"

def process_skills_string(skills_str):
    """
    Traite une chaîne contenant des compétences réparties sur plusieurs lignes.
    Fusionne les lignes de la même compétence si :
      - La ligne précédente se termine par une virgule,
      - OU si la ligne suivante débute par une lettre minuscule,
      - OU si la ligne suivante contient une virgule.
    Puis, retourne une chaîne où chaque compétence est séparée par une virgule.
    """
    lines = [line.strip() for line in skills_str.splitlines() if line.strip()]
    skills_list = []
    current_skill = ""
    for line in lines:
        if not current_skill:
            current_skill = line
        else:
            if current_skill.endswith(",") or line[0].islower() or ("," in line):
                current_skill += " " + line
            else:
                skills_list.append(current_skill)
                current_skill = line
    if current_skill:
        skills_list.append(current_skill)
    # Nettoyer les espaces superflus et supprimer les éventuels deux-points à la fin
    skills_list = [skill.rstrip(":").strip() for skill in skills_list]
    return ", ".join(skills_list)

def process_skills(json_data):
    """
    Traite le champ "skills" selon son format :
      - Si c'est une chaîne, on vérifie si elle contient des catégories séparées par ":".
        Si après les ":" aucune valeur n'est présente (ex. "Catégorie :" sans contenu),
        on extrait uniquement la partie avant le ":" et on traite le tout comme une liste simple.
      - Si c'est une liste, on joint les éléments avec des virgules.
      - Si c'est un dictionnaire, on applique ce traitement à chacune des catégories.
    """
    skills = json_data.get("skills", None)
    if skills is None:
        return json_data

    if isinstance(skills, str):
        if ":" in skills:
            lines = [line.strip() for line in skills.splitlines() if line.strip()]
            # Vérifier s'il existe au moins une ligne où le contenu après ":" n'est pas vide
            has_non_empty_value = any(
                len(line.split(":", 1)[1].strip()) > 0 for line in lines if ":" in line
            )
            if has_non_empty_value:
                # Traiter comme dictionnaire
                skills_dict = {}
                for line in lines:
                    if ":" in line:
                        category, value = line.split(":", 1)
                        skills_dict[category.strip()] = value.strip()
                    else:
                        if "Autres" not in skills_dict:
                            skills_dict["Autres"] = []
                        skills_dict["Autres"].append(line.strip())
                json_data["skills"] = skills_dict
            else:
                # Aucune valeur après ":", on extrait uniquement la partie avant le ":"
                cleaned_lines = [line.split(":", 1)[0].strip() if ":" in line else line for line in lines]
                json_data["skills"] = ", ".join(cleaned_lines)
        else:
            # Si pas de ":", traiter comme une liste simple
            lines = [line.strip() for line in skills.splitlines() if line.strip()]
            json_data["skills"] = ", ".join(lines)
    elif isinstance(skills, list):
        json_data["skills"] = ", ".join(skills)
    elif isinstance(skills, dict):
        for key, value in skills.items():
            if isinstance(value, str):
                # On peut réutiliser la fonction process_skills_string pour nettoyer la chaîne
                skills[key] = process_skills_string(value)
            elif isinstance(value, list):
                skills[key] = ", ".join(value)
    return json_data


def generate_pdf_from_json(json_data, output_file):
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = 'Helvetica'
    styles['Normal'].fontSize = 10
    styles['Normal'].leading = 12
    styles.add(ParagraphStyle(name='Section', parent=styles['Normal'],
                              fontName='Helvetica-Bold', fontSize=12,
                              textColor=colors.black, alignment=1, spaceAfter=12))
    styles.add(ParagraphStyle(name='Bold', parent=styles['Normal'],
                              fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Center', parent=styles['Normal'], alignment=1))
    styles.add(ParagraphStyle(name='Right', parent=styles['Normal'], alignment=2))
    
    def create_section_title(title_text):
        title_para = Paragraph(title_text, styles['Section'])
        title_table = Table([[title_para]], colWidths=[6*inch])
        title_table.setStyle(TableStyle([
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("BOX", (0,0), (-1,-1), 1, colors.turquoise),
            ("BOTTOMPADDING", (0,0), (-1,-1), 12),
            ("TOPPADDING", (0,0), (-1,-1), 12)
        ]))
        return title_table

    story = []
    
    def draw_banner(canvas_obj, doc_obj):
        try:
            banner_path = "Background.png"
            if os.path.exists(banner_path):
                banner_img = ImageReader(banner_path)
                banner_height = 2 * inch
                canvas_obj.drawImage(banner_img, 0, A4[1] - banner_height,
                                       width=A4[0], height=banner_height)
            else:
                logging.warning(f"Bannière introuvable : {banner_path}")
                banner_height = 2 * inch
        except Exception as e:
            logging.error(f"Erreur lors du chargement de la bannière : {e}")
            banner_height = 2 * inch

        title_style = ParagraphStyle(
            name='HeaderTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            alignment=0,
            leading=24,
            textColor=colors.white
        )
        
        job_title = json_data.get('job_title', '').replace('\n', ' ').strip() or "CV Title"
        title_para = Paragraph(job_title, title_style)
        available_width = A4[0] - 2 * inch
        w, h = title_para.wrap(available_width, 100)
        vertical_offset = 20
        title_y = A4[1] - (2 * inch)/2 - h/2 + vertical_offset
        header_x = 4.5 * cm
        title_para.drawOn(canvas_obj, header_x, title_y)
        
        full_name = json_data.get('full_name', '').strip()
        if full_name:
            parts = full_name.split()
            initials = parts[0][0].upper() + "." + parts[-1][0].upper() if len(parts) >= 2 else full_name[0].upper()
        else:
            initials = "?"
        canvas_obj.setFont("Helvetica-Bold", 14)
        years_experience = str(json_data.get('years_of_experience', '')).replace('\n', ' ').strip()
        experience_text = f"{initials} : {years_experience} XP"
        canvas_obj.setFillColor(colors.white)
        canvas_obj.drawString(header_x, title_y - 20, experience_text)
        icon_y_position = A4[1] - inch - 60
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(80, icon_y_position, "01 40 76 01 49")
        canvas_obj.drawString(260, icon_y_position, "heptasys@heptasys.com")
        canvas_obj.drawString(470, icon_y_position, "www.heptasys.com")
    
    story.append(Spacer(1, 100))
    
    # Formation & Certifications
    story.append(create_section_title("Formation & Certifications"))
    story.append(Spacer(1, 12))
    if json_data.get('education'):
        education_rows = []
        for edu in json_data.get('education', []):
            degree = edu.get('degree', '').replace('\n', ' ')
            institution = edu.get('institution', '').replace('\n', ' ')
            year = str(edu.get('year_of_completion', '')).strip()
            left_text = Paragraph(f"<b>{degree} à {institution}</b>", styles['Normal'])
            right_text = Paragraph(year, styles['Normal'])
            education_rows.append([left_text, right_text])
        if education_rows:
            edu_table = Table(education_rows, colWidths=[4.5*inch, 1.5*inch])
            edu_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6)
            ]))
            story.append(edu_table)
            story.append(Spacer(1, 12))
    # Certifications : affichage en gras sur une seule colonne
    if json_data.get('certifications'):
        certification_rows = [[Paragraph(cert, styles['Bold'])] for cert in json_data.get('certifications', [])]
        if certification_rows:
            certs_table = Table(certification_rows, colWidths=[6*inch])
            certs_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6)
            ]))
            story.append(certs_table)
            story.append(Spacer(1, 12))
    
    # Compétences techniques
    story.append(create_section_title("Compétences techniques"))
    story.append(Spacer(1, 12))
    skills_section = json_data.get('skills', None)
    if isinstance(skills_section, dict) and skills_section:
        for category_key, skills in skills_section.items():
            cat_title = category_key.replace('_', ' ').title()
            # Afficher la clé et les valeurs sur la même ligne
            story.append(Paragraph(f"<b>{cat_title} :</b> {skills}", styles['Normal']))
            story.append(Spacer(1, 6))
    elif isinstance(skills_section, str) and skills_section:
        # Afficher la clé par défaut et les compétences sur la même ligne
        story.append(Paragraph(f"{skills_section}", styles['Normal']))
    else:
        story.append(Paragraph("Aucune compétence technique extraite.", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Expériences professionnelles
    story.append(create_section_title("Expériences professionnelles"))
    story.append(Spacer(1, 12))
    for exp in json_data.get('professional_experience', []):
        date_range = exp.get('date_range', '').strip() or "Date non renseignée"
        company_name = exp.get('company_name', '').replace('\n', ' ').strip()
        mission = exp.get('mission', '').replace('\n', ' ').strip() or "Poste non renseigné"
        exp_table = Table([
            [Paragraph(f"<b>{date_range}</b>", styles['Normal']),
             Paragraph(f"<b>{company_name}</b>", styles['Normal'])]
        ], colWidths=[3.0 * inch, 3.0 * inch])
        exp_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6)
        ]))
        story.append(exp_table)
        story.append(Paragraph(mission, styles['Bold']))
        if exp.get('tasks'):
            story.append(Paragraph("Tâches :", styles['Bold']))
            for task in exp.get('tasks'):
                story.append(Paragraph("• " + task.replace('\n', ' '), styles['Normal']))
        if exp.get('tech_tools'):
            tech_tools = ", ".join(exp.get('tech_tools', []))
            story.append(Paragraph("<font color='turquoise'><b>Outils</b></font> : " + tech_tools, styles['Normal']))
        story.append(Spacer(1, 12))
    
    doc.build(story, onFirstPage=draw_banner)



def remove_blank_paragraphs(docx_file_path):
    doc = Document(docx_file_path)
    # Parcourir une copie de la liste pour éviter des problèmes lors de la suppression
    for paragraph in list(doc.paragraphs):
        # Si le texte est vide…
        if not paragraph.text.strip():
            # Vérifier si le paragraphe contient des images (éléments "w:drawing")
            if paragraph._element.xpath('.//w:drawing'):
                continue  # On ne supprime pas le paragraphe s'il contient des images
            # Sinon, supprimer le paragraphe vide
            p = paragraph._element
            p.getparent().remove(p)
    doc.save(docx_file_path)


def convert_pdf_to_docx(pdf_path, docx_path):
    try:
        cv = Converter(pdf_path)
        cv.convert(docx_path, start=0)
        cv.close()
        remove_blank_paragraphs(docx_path)
        logging.info(f"Conversion réussie : {pdf_path} -> {docx_path}")
        return True
    except Exception as e:
        logging.error(f"Erreur lors de la conversion du PDF en DOCX : {e}")
        return False



def adjust_docx_top_margin(docx_file_path, top_margin_inch=0.5):
    
    
    doc = Document(docx_file_path)
    for section in doc.sections:
        section.top_margin = Inches(top_margin_inch)
    doc.save(docx_file_path)


def adjust_docx_spacing(docx_file_path):
    doc = Document(docx_file_path)
    
    for paragraph in doc.paragraphs:
        raw_text = paragraph.text.strip()  # texte original
        text = raw_text.lower()            # texte en minuscules pour la comparaison

        # Débogage éventuel : décommenter pour voir les contenus
        # print(f"DEBUG: [{raw_text}]")

        # 1. Ajouter de l'espace APRÈS le bloc contacts
        if ("heptasys@heptasys.com" in text 
            or "01 40 76 01 49" in text 
            or "www.heptasys.com" in text):
            paragraph.paragraph_format.space_after = Pt(50)

        # 2. Ajouter de l'espace AVANT "Formation & Certifications"
        #    On recherche "formation" et "certification" n'importe où dans le paragraphe
        #    afin de gérer d'éventuelles variations d'accents, majuscules, etc.
        if "formation" in text and "certification" in text:
            paragraph.paragraph_format.space_before = Pt(100)  # Ajustez la valeur à vos besoins

    doc.save(docx_file_path)


def upload_to_blob_storage(file_path, blob_name):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        logging.info(f"Fichier {blob_name} uploadé vers Azure Blob Storage.")
    except Exception as e:
        logging.error(f"Erreur lors de l'upload vers Blob Storage : {e}")

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
        json_data = process_skills(json_data)
        # Remplacer les certifications par une extraction directe par regex
        json_data = override_certifications_with_regex(extracted_text, json_data)
        pdf_file_name = generate_pdf_filename(json_data, filename)
        pdf_file_path = os.path.join(tempfile.gettempdir(), pdf_file_name)
        generate_pdf_from_json(json_data, pdf_file_path)
        logging.info(f"PDF généré à {pdf_file_path}")
        docx_file_name = pdf_file_name.replace('.pdf', '.docx')
        docx_file_path = os.path.join(tempfile.gettempdir(), docx_file_name)
        if not convert_pdf_to_docx(pdf_file_path, docx_file_path):
            logging.error("Échec de la conversion du PDF en DOCX")
            return jsonify({"error": "Échec de la conversion du PDF en DOCX"}), 500
        logging.info(f"DOCX généré à {docx_file_path}")
        adjust_docx_top_margin(docx_file_path, top_margin_inch=0.5)
        adjust_docx_spacing(docx_file_path)
        logging.info("Marge supérieure et espacement ajustés dans le fichier DOCX.")
        upload_to_blob_storage(pdf_file_path, pdf_file_name)
        upload_to_blob_storage(docx_file_path, docx_file_name)
        logging.info(f"PDF et DOCX uploadés vers Blob Storage sous les noms {pdf_file_name} et {docx_file_name}")
        pdf_sas_url = generate_sas_token(pdf_file_name)
        docx_sas_url = generate_sas_token(docx_file_name)
        if pdf_sas_url and docx_sas_url:
            logging.info(f"SAS URLs générés : PDF - {pdf_sas_url}, DOCX - {docx_sas_url}")
            return jsonify({
                "pdf_sas_url": pdf_sas_url,
                "docx_sas_url": docx_sas_url
            }), 200
        else:
            logging.error("Échec de la génération des SAS tokens")
            return jsonify({"error": "Échec de la génération des SAS tokens"}), 500
    else:
        logging.error("Fichier non valide ou extension non autorisée")
        return jsonify({"error": "Fichier non valide ou extension non autorisée"}), 400

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
