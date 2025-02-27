# Documentation du Système de Traitement de CV

## 1. Introduction

Ce système permet de traiter des fichiers de CV (PDF, DOCX, images) afin d'en extraire automatiquement des informations structurées. Il inclut les étapes suivantes :

- Extraction du texte depuis le fichier source (PDF, DOCX ou image).
- Analyse et structuration des données avec l'API Azure OpenAI.
- Génération d'un fichier PDF formaté avec ReportLab.
- Conversion du PDF en DOCX avec pdf2docx.
- Upload des fichiers générés sur Azure Blob Storage avec génération de SAS URLs pour un accès sécurisé.

### Différences entre les branches `template` et `template_docx`

- **Branche `template`** : Retourne uniquement le lien SAS pour le fichier PDF généré.
- **Branche `template_docx`** : Retourne deux liens SAS (PDF et DOCX) pour offrir un accès modifiable au format DOCX.

---

## 2. Architecture & Technologies Utilisées

- **Python** : Langage de programmation principal.
- **Flask** : Framework pour exposer les endpoints API.
- **Azure OpenAI** : Extraction et structuration des données.
- **Azure Key Vault** : Sécurisation des secrets (API key, endpoints, etc.).
- **Azure Blob Storage** : Stockage des fichiers générés.
- **PyMuPDF (fitz)** : Extraction de texte depuis les fichiers PDF.
- **python-docx** : Lecture et traitement des fichiers DOCX.
- **pytesseract** : OCR pour extraction de texte depuis des images.
- **ReportLab** : Génération des fichiers PDF.
- **pdf2docx** : Conversion du PDF en DOCX.
- **uuid** : Génération de noms de fichiers uniques.
- **dotenv** : Gestion des variables d'environnement.

---

## 3. Fonctionnalités Principales

### Extraction du Texte

```python
extract_text(file_path)
```

- **PDF** : Utilisation de PyMuPDF.
- **DOCX** : Extraction du texte et des tableaux.
- **Images** : OCR via pytesseract.

### Extraction des Informations Structurées

```python
extract_info_to_json(text)
```

- Envoi du texte à l’API Azure OpenAI avec un prompt spécifique.
- Extraction des données sous format JSON :
  - **Titre du poste, nom complet, années d’expérience.**
  - **Coordonnées (téléphone, e-mail, site web).**
  - **Formations (diplômes, institutions, années).**
  - **Expériences professionnelles (dates, entreprise, missions, tâches, outils).**
  - **Compétences et certifications.**

### Génération du PDF et Conversion en DOCX

- **PDF** : Création avec ReportLab.
- **DOCX** : Conversion via pdf2docx.

### Upload vers Azure Blob Storage

- **Upload des fichiers (PDF/DOCX).**
- **Génération de SAS URLs pour un accès sécurisé.**

---

## 4. Endpoints et Flux de Traitement

### Endpoint `/template` (POST)

1. **Validation et Sauvegarde** : Vérification et stockage temporaire du fichier.
2. **Extraction du Texte** : Utilisation de `extract_text()`.
3. **Extraction Structurée** : Analyse via `extract_info_to_json()`.
4. **Génération du PDF** : Création avec `generate_pdf_from_json()`.
5. **Conversion PDF → DOCX** : Avec `convert_pdf_to_docx()`.
6. **Upload sur Azure Blob Storage** : Stockage sécurisé des fichiers.
7. **Génération des SAS URLs** : Renvoi des liens sécurisés en réponse.

---

## 5. Configuration et Déploiement

### Prérequis

- **Python 3.x**
- **Bibliothèques nécessaires** (installables via `pip`)

```bash
pip install azure-keyvault-secrets azure-identity azure-storage-blob openai \
            PyMuPDF python-docx pytesseract reportlab pdf2docx flask flask-cors python-dotenv uuid
```

- **Fichier `.env`** contenant les clés et connexions (API key, endpoints, etc.).

### Exécution

```bash
python convert.py
```

Le serveur sera accessible sur **http://0.0.0.0:5001**.

---

## 6. Modifications Apportées

- **Extraction améliorée** : Ajout de l’extraction du contenu des tableaux dans les DOCX.
- **Prompt d’extraction optimisé** : Meilleure structuration des expériences professionnelles.
- **Conversion PDF → DOCX intégrée** : Ajout de pdf2docx pour obtenir une version modifiable.
- **Upload sécurisé** : Maintien des SAS URLs pour un accès contrôlé.

### Remarque sur Chat Completions et Tokens

- **Erreur 400 sur `chatCompletion` avec `gpt-35-turbo-instruct`** : Nécessité d'utiliser un modèle compatible.
- **Gestion du dépassement de tokens** : Possibilité de découpage du texte en segments plus petits.
