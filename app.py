import json
import logging
from flask import Flask, request, jsonify, Response
from flask_cors import CORS, cross_origin
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import io
import docx2txt
import PyPDF2
import traceback
from pymongo import MongoClient
 
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://talent.heptasys.com"}}, allow_headers=["Content-Type", "Authorization", "X-Requested-With"])
 
logging.basicConfig(level=logging.INFO)
 
# Azure Key Vault for secrets management
key_vault_name = 'AI-vault-hepta'
key_vault_uri = f"https://{key_vault_name}.vault.azure.net/"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)
 
# MongoDB setup
mongo_uri = secret_client.get_secret('MONGOsearchURI').value
mongo_client = MongoClient(mongo_uri)
db = mongo_client['AzureBlob']
 
# OpenAI client setup using Azure
api_key = secret_client.get_secret('AZUREopenaiAPIkey').value
azure_endpoint = secret_client.get_secret('AZUREopenaiENDPOINT').value
azure_openai_client = AzureOpenAI(api_key=api_key, api_version="2024-02-15-preview", azure_endpoint=azure_endpoint)
 
def extract_text(file):
    if 'pdf' in file.content_type:
        return extract_text_from_pdf(file)
    elif 'word' in file.content_type or file.filename.endswith('.docx'):
        return extract_text_from_docx(file)
    else:
        raise ValueError("Unsupported file format")
 
def extract_text_from_pdf(file):
    reader = PyPDF2.PdfReader(file.stream)
    text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
    return text
 
def extract_text_from_docx(file):
    file_content = file.read()
    file_buffer = io.BytesIO(file_content)
    return docx2txt.process(file_buffer)
 
def analyze_resume(resume_text, job_description):
    messages = [
        {
            "role": "system",
            "content": "Take a deep breath, act as a CV and job posting comparer, write in full sentences in French, Évaluer la correspondance du CV suivant avec le descriptif ci-dessus en donnant pour chaque tâche et technologie requise dans le descriptif le pourcentage de correspondance et donner le pourcentage global enfin donner ce qu'il faut ajouter sur le CV pour avoir un meilleur matching.\n\n"
            "Vous êtes un recruteur professionnel strict et expert en analyse de CV. "
            "Votre tâche est d'analyser le CV ci-dessous par rapport à une description de poste spécifique et de fournir une analyse rigoureuse et détaillée. "
            "Veuillez extraire uniquement les informations suivantes du CV : email, téléphone, adresse, compétences clés, expériences professionnelles principales. "
            "Ensuite, fournissez un score de correspondance détaillé entre 0 et 100, une recommandation par 'oui' ou 'non' pour l'adéquation, "
            "et une justification détaillée pour chaque tâche et technologie requise dans le descriptif. "
            "N'acceptez que les correspondances explicites; n'envisagez pas de potentiel futur.\n\n"
            "1. Email\n"
            "2. Téléphone\n"
            "3. Adresse\n"
            "4. Tous les Compétences clés (sous forme de points)\n"
            "5. Tous les Expériences professionnelles principales\n"
            "6. Score (from 1 to 100)\n"    
            "7. Recommendation (Oui ou Non)\n"
            "8. A short but meaningful justification in French\n"
            "9. Pour améliorer le CV"
        },
        {"role": "user", "content": f"Description du poste : {job_description}"},
        {"role": "user", "content": f"CV : {resume_text}"}
    ]
 
    def generate():
        try:
            response = azure_openai_client.chat.completions.create(
                model="Best",
                messages=messages,
                max_tokens=3000,
                temperature=0,
                stream=True
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    # Log the content to the terminal
                    print(content, end='', flush=True)
                    yield f"data: {json.dumps({'chunk': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
 
    return Response(generate(), content_type='text/event-stream')
 
 
 
@app.route('/analyse-cv', methods=['POST'])
@cross_origin()
def analyse_cv():
    logging.info("Received a request at /analyse-cv")
    try:
        file = request.files.get('cv')
        job_description = request.form.get('jobDescription')
 
        if not file:
            logging.error("No CV file provided")
            return jsonify({'error': "No CV file provided"}), 400
        if not job_description:
            logging.error("No job description provided")
            return jsonify({'error': "No job description provided"}), 400
 
        resume_text = extract_text(file)
        return analyze_resume(resume_text, job_description)
 
    except Exception as e:
        logging.error(f"Error processing request: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
 
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
