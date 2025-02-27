Documentation du Système de Traitement de CV 
1. Introduction 

Ce système est conçu pour traiter des fichiers de CV (formats PDF, DOCX, images) afin d'en extraire automatiquement des informations structurées. Le flux complet inclut : 

Extraction du texte à partir du fichier source (PDF, DOCX ou image). 
Extraction des informations structurées via l'API Azure OpenAI (à l'aide d'un prompt personnalisé). 
Génération d'un fichier PDF formaté avec ReportLab, présentant les données extraites. 
Conversion du PDF généré en DOCX grâce à la bibliothèque pdf2docx. 
Upload des fichiers générés (PDF et DOCX) sur Azure Blob Storage et génération de SAS URLs pour un accès sécurisé. 
La différence entre les branches « template » et « template_docx » réside dans les fichiers renvoyés après le traitement : 

Branche template : 
Elle retourne uniquement le lien SAS pour le fichier PDF généré. 
Branche template_docx : 
Elle renvoie deux liens SAS, l’un pour le fichier PDF et l’autre pour le fichier DOCX. Cette approche permet de faciliter les modifications, en offrant un accès au format modifiable (DOCX) en plus du format final PDF. 
2. Architecture & Technologies Utilisées 

Python pour le développement. 
Flask : Framework web pour exposer les endpoints (API). 
Azure OpenAI : Pour l’extraction et la structuration des données à partir du texte. 
Azure Key Vault : Pour sécuriser et récupérer les secrets (API key, endpoints, chaîne de connexion). 
Azure Blob Storage : Pour stocker les fichiers générés et fournir des accès sécurisés via SAS URLs. 
PyMuPDF (fitz) : Pour extraire le texte des fichiers PDF. 
python-docx : Pour lire les fichiers DOCX. 
pytesseract : Pour l'extraction de texte à partir d'images. 
ReportLab : Pour la génération du fichier PDF. 
pdf2docx : Pour convertir le PDF généré en fichier DOCX. 
uuid : Pour générer des noms de fichiers uniques afin d’éviter toute collision. 
dotenv : Pour charger les variables d'environnement depuis un fichier .env. 
3. Fonctionnalités Principales 

Extraction du Texte 

extract_text(file_path) 
Permet d’extraire le texte d’un fichier selon son type (PDF, DOCX ou image). 
Pour les PDF, utilise PyMuPDF. 
Pour les DOCX, lit tous les paragraphes et les contenus des tableaux. 
Pour les images, utilise pytesseract. 
Extraction des Informations Structurées 

extract_info_to_json(text) 
Envoie le texte extrait à l’API Azure OpenAI avec un prompt détaillé pour extraire : 
Le titre du poste, le nom complet, et les années d’expérience. 
Les coordonnées (téléphone, e-mail, site web). 
Les formations (diplômes, institutions, année). 
Les expériences professionnelles (période, entreprise, mission, tâches et outils). 
Les compétences et certifications. 
Le prompt demande une sortie strictement au format JSON. 
Nettoyage et Sauvegarde du JSON 

clean_and_save_json(raw_json_text, file_path) 
Valide et enregistre la chaîne JSON obtenue dans un fichier. 
Génération du PDF 

generate_pdf_from_json(json_data, output_file) 
Utilise ReportLab pour créer un PDF formaté à partir du JSON extrait. 
Intègre des sections pour la formation, les compétences, et les expériences professionnelles. 
Ajoute une bannière et des informations de contact dans l’en-tête. 
Conversion PDF → DOCX 

convert_pdf_to_docx(pdf_path, docx_path) 
Utilise la bibliothèque pdf2docx pour convertir le PDF généré en fichier DOCX. 
Upload vers Azure Blob Storage et Génération des SAS URLs 

upload_to_blob_storage(file_path, blob_name) 
Upload le fichier (PDF ou DOCX) vers Azure Blob Storage dans le container spécifié. 
generate_sas_token(blob_name) 
Génère une URL avec SAS token pour accéder au fichier de manière sécurisée. 
4. Endpoints et Flux de Traitement 

Endpoint /template (POST) 

Ce endpoint gère l’upload du fichier et l’ensemble du processus de traitement : 

Validation et Sauvegarde 
Le fichier uploadé est vérifié (extension autorisée) et sauvegardé temporairement avec un nom unique. 
Extraction du Texte 
Le texte est extrait à l’aide de extract_text(). 
Extraction Structurée 
Le texte est envoyé à l’API Azure OpenAI via extract_info_to_json(), et le résultat est sauvegardé sous forme de JSON. 
Génération du PDF 
À partir du JSON, un PDF est généré avec generate_pdf_from_json(). 
Conversion PDF → DOCX 
Le PDF est converti en DOCX grâce à convert_pdf_to_docx(). 
Upload sur Azure Blob Storage 
Les fichiers PDF et DOCX sont uploadés vers Azure Blob Storage. 
Génération des SAS URLs 
Des URLs sécurisées (SAS URLs) pour les fichiers uploadés sont générées et renvoyées en réponse. 
5. Configuration et Déploiement 

Prérequis 

Python 3.x 
Bibliothèques requises (installables via pip) : 
azure-keyvault-secrets, azure-identity, azure-storage-blob, openai, PyMuPDF, python-docx, pytesseract, reportlab, pdf2docx, flask, flask-cors, python-dotenv, uuid 
Fichier .env contenant les variables d'environnement pour les clés et chaînes de connexion (API key, endpoints, connect string, etc.) 
Exécution 

Pour lancer le serveur en mode développement, exécutez : 

python convert.py 

Le serveur sera accessible sur http://0.0.0.0:5001. 

6. Modifications Apportées par Rapport au Code Initial 

Gestion des Formats : 
L’extraction du texte a été améliorée pour inclure le contenu des tableaux dans les fichiers DOCX. 
Prompt d’Extraction : 
Le prompt utilisé dans extract_info_to_json a été affiné pour extraire plus précisément les informations relatives aux expériences professionnelles (date_range, company_name, mission, tasks, tech_tools) et autres sections importantes. 
Conversion PDF vers DOCX : 
La fonctionnalité de conversion du PDF généré en fichier DOCX a été intégrée via la bibliothèque pdf2docx, offrant ainsi un double format de sortie pour les CV traités. 
Upload et SAS URLs : 
Le processus d’upload vers Azure Blob Storage et la génération de SAS URLs ont été maintenus et intégrés dans le flux complet pour permettre un accès sécurisé aux fichiers générés. 
Remarque sur l'Intégration de Chat Completions et la Gestion du Dépassement de Tokens : 
Chat Completions : 
Lors de l'intégration de la fonction chatCompletions, une erreur 400 est retournée avec le message : 
"The chatCompletion operation does not work with the specified model, gpt-35-turbo-instruct. Please choose different model and try again." 
Cela signifie que l'opération de type "chat completions" n'est pas compatible avec le modèle gpt-35-turbo-instruct. Pour utiliser des fonctionnalités de chat, il faut soit choisir un autre modèle adapté à l'opération chat, soit utiliser l'endpoint de completions classique pour ce modèle. 
Gestion du Dépassement de Tokens : 
Des fonctions supplémentaires (non présentées dans ce code, mais pouvant être intégrées) ont été envisagées pour diviser le texte en morceaux si celui-ci est volumineux ou contient des caractères spéciaux. En effet, un texte important peut impacter la validité du JSON généré par l’API ou dépasser la limite de tokens prévue. Cette approche consiste à découper le texte et à traiter chaque morceau séparément pour ensuite fusionner les résultats. 
 

 
