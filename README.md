**DocumentationduSystèmede** **Traitement** **deCV**

**1.Introduction**

Cesystèmeestconçupour traiter desfichiersdeCV (formatsPDF,DOCX,images)
afin
d'enextraireautomatiquementdesinformationsstructurées.Lefluxcompletinclut:

> • **Extractiondu** **texte**àpartir dufichier source(PDF,DOCXouimage).
>
> •
> **Extractiondesinformationsstructurées**vial'APIAzureOpenAI(àl'aided'un
> promptpersonnalisé).
>
> • **Générationd'unfichierPDF**
> formatéavecReportLab,présentantlesdonnées extraites.
>
> •     **Conversiondu** **PDFgénéréenDOCX**
> grâceàlabibliothèquepdf2docx. •     **Upload**
> **desfichiersgénérés(PDFet** **DOCX)** **surAzureBlob** **Storage** et
>
> générationdeSASURLspour unaccèssécurisé.

Ladifférenceentrelesbranches« template» et« template_docx» résidedansles
fichiersrenvoyésaprèsletraitement:

> • **Branchetemplate** :
>
> ElleretourneuniquementlelienSASpour lefichier PDF généré. •
> **Branchetemplate_docx** :
>
> EllerenvoiedeuxliensSAS,l’unpour lefichier PDFetl’autrepour lefichier
> DOCX.Cetteapprochepermetdefaciliter lesmodifications,enoffrantunaccès
> auformatmodifiable(DOCX) enplusduformatfinalPDF.

**2.Architecture&TechnologiesUtilisées**

> • **Python**pour ledéveloppement.
>
> • **Flask**:Frameworkweb pour exposer lesendpoints(API).
>
> • **AzureOpenAI**:Pour l’extractionetlastructurationdesdonnéesàpartir
> du texte.
>
> • **AzureKeyVault**:Pour sécuriser etrécupérer
> lessecrets(APIkey,endpoints, chaînedeconnexion).
>
> • **AzureBlob** **Storage** :Pour stocker lesfichiersgénérésetfournir
> desaccès sécurisésviaSASURLs.
>
> • **PyMuPDF(fitz)**:Pour extraireletextedesfichiersPDF. •
> **python-docx**:Pour lirelesfichiersDOCX.
>
> • **pytesseract**:Pourl'extractiondetexteàpartir d'images. •
> **ReportLab**:Pour lagénérationdufichier PDF.
>
> • **pdf2docx**:Pour convertir lePDF généréenfichier DOCX.
>
> • **uuid**:Pour générer desnomsdefichiersuniquesafind’éviter
> toutecollision. • **dotenv**:Pour charger
> lesvariablesd'environnementdepuisunfichier .env.

**3.Fonctionnalités** **Principales**

**ExtractionduTexte**

> • **extract_text(file_path)**
>
> Permetd’extraireletexted’unfichier selonsontype(PDF,DOCXouimage). o
> Pour lesPDF,utilisePyMuPDF.
>
> o Pour lesDOCX,littouslesparagraphesetlescontenusdestableaux. o Pour
> lesimages,utilisepytesseract.

**Extractiondes** **Informations** **Structurées**

> • **extract_info_to_json(text)**
> Envoieletexteextraitàl’APIAzureOpenAIavecunpromptdétaillépour extraire
> :
>
> o Letitreduposte,lenom complet,etlesannéesd’expérience. o
> Lescoordonnées(téléphone,e-mail,siteweb).
>
> o Lesformations(diplômes,institutions,année).
>
> o Lesexpériencesprofessionnelles(période,entreprise,mission,tâcheset
> outils).

o Lescompétencesetcertifications.
LepromptdemandeunesortiestrictementauformatJSON.

**Nettoyage** **et** **Sauvegarde** **duJSON**

> • **clean_and_save_json(raw_json_text,file_path)**
> ValideetenregistrelachaîneJSON obtenuedansunfichier.

**GénérationduPDF**

> • **generate_pdf_from_json(json_data,output_file)**
>
> UtiliseReportLab pour créer unPDF formatéàpartir duJSON extrait.
>
> o Intègredessectionspour laformation,lescompétences,etles
> expériencesprofessionnelles.
>
> o Ajouteunebannièreetdesinformationsdecontactdansl’en-tête.

**ConversionPDF** **→DOCX**

> • **convert_pdf_to_docx(pdf_path,docx_path)**
> Utiliselabibliothèquepdf2docxpour convertir lePDF généréenfichier
> DOCX.

**Uploadvers** **Azure** **Blob** **Storage** **et** **Générationdes**
**SASURLs**

> • **upload_to_blob_storage(file_path,blob_name)**
>
> Upload lefichier (PDF ouDOCX) versAzureBlob Storagedanslecontainer
> spécifié.
>
> • **generate_sas_token(blob_name)**
>
> GénèreuneURL avecSAStokenpour accéder aufichier demanièresécurisée.

**4.Endpoints** **etFluxdeTraitement**

**Endpoint** **/template** **(POST)**

Ceendpointgèrel’uploaddufichier etl’ensembleduprocessusdetraitement:

> 1\. **Validationet** **Sauvegarde**
>
> Lefichier uploadéestvérifié(extensionautorisée) etsauvegardé
> temporairementavecunnom unique.
>
> 2\. **Extractiondu** **Texte**
> Letexteestextraitàl’aidedeextract_text().
>
> 3\. **ExtractionStructurée**
> Letexteestenvoyéàl’APIAzureOpenAIviaextract_info_to_json(),etlerésultat
> estsauvegardésousformedeJSON.
>
> 4\. **Générationdu** **PDF**
>
> ÀpartirduJSON,unPDF estgénéréavecgenerate_pdf_from_json(). 5.
> **ConversionPDF→DOCX**
>
> LePDF estconvertienDOCXgrâceàconvert_pdf_to_docx(). 6. **Upload**
> **surAzureBlob** **Storage**
>
> LesfichiersPDF etDOCXsontuploadésversAzureBlob Storage. 7.
> **GénérationdesSASURLs**
>
> DesURLssécurisées(SASURLs) pour les fichiersuploadéssontgénéréeset
> renvoyéesenréponse.

**5.ConfigurationetDéploiement**

**Prérequis**

> • Python3.x
>
> • Bibliothèquesrequises(installablesviapip) :
>
> o azure-keyvault-secrets,azure-identity,azure-storage-blob,openai,
> PyMuPDF,python-docx,pytesseract,reportlab,pdf2docx,flask,flask-cors,python-dotenv,uuid
>
> • Fichier .envcontenantlesvariablesd'environnementpour
> lesclésetchaînesde connexion(APIkey,endpoints,connectstring,etc.)

**Exécution**

Pour lancer leserveur enmodedéveloppement,exécutez :

pythonconvert.py

Leserveur seraaccessiblesur
[<u>http://0.0.0.0:5001</u>.](http://0.0.0.0:5001/)

**6.Modifications** **ApportéesparRapportau** **Code** **Initial**

> • **GestiondesFormats** :
>
> L’extractiondutexteaétéamélioréepour inclurelecontenudestableauxdans
> lesfichiersDOCX.
>
> • **Promptd’Extraction** :
> Lepromptutilisédansextract_info_to_jsonaétéaffinépourextraireplus
> précisémentlesinformationsrelativesauxexpériencesprofessionnelles
> (date_range,company_name,mission,tasks,tech_tools) etautressections
> importantes.
>
> • **ConversionPDFversDOCX** :
>
> LafonctionnalitédeconversionduPDF généréenfichier DOCXaétéintégréevia
> labibliothèquepdf2docx,offrantainsiundoubleformatdesortiepour lesCV
> traités.
>
> • **Upload** **et** **SASURLs** :
>
> Leprocessusd’upload versAzureBlob StorageetlagénérationdeSASURLsont
> étémaintenusetintégrésdanslefluxcompletpour permettreunaccèssécurisé
> auxfichiersgénérés.
>
> • **Remarquesurl'IntégrationdeChat** **Completionset** **laGestiondu**
> **DépassementdeTokens**:
>
> o **Chat** **Completions** :
> Lorsdel'intégrationdelafonction*chatCompletions*,uneerreur 400est
> retournéeaveclemessage:
>
> *"ThechatCompletionoperationdoesnot* *workwiththespecified* *model,*
> *gpt-35-turbo-instruct.Pleasechoosedifferent* *modeland* *tryagain."*
> Celasignifiequel'opérationdetype"chatcompletions"n'estpas
> compatibleaveclemodèlegpt-35-turbo-instruct.Pour utiliser des
> fonctionnalitésdechat,ilfautsoitchoisir unautremodèleadaptéà
> l'opérationchat,soitutiliser l'endpointde *completions*classiquepour
> ce modèle.
>
> o **Gestiondu** **Dépassement** **deTokens** :
> Desfonctionssupplémentaires(nonprésentéesdanscecode,mais
> pouvantêtreintégrées) ontétéenvisagéespour diviser letexteen
> morceauxsicelui-ciestvolumineuxoucontientdescaractèresspéciaux.
> Eneffet,untexteimportantpeutimpacter lavaliditéduJSON générépar
> l’APIoudépasser lalimitedetokensprévue.Cetteapprocheconsisteà découper
> letexteetàtraiter chaquemorceauséparémentpour ensuite fusionner
> lesrésultats.
