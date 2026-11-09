# Comparaison et apprentissage ? Phase 1

Comparaison conceptuelle : les fichiers du projet From Scratch n'ont pas ete inspectes. LangGraph et LangChain ne sont pas encore installes ni utilises.

| Fonctionnalite | Avec framework | Sans framework |
|---|---|---|
| Technologie | Pydantic BaseModel via pydantic_settings.BaseSettings, SettingsConfigDict ; pytest | os.environ, dataclasses, parseur dotenv et assertions manuelles (ou les memes outils de configuration/tests) |
| Responsabilite | Chargement dotenv/environnement, priorites, validation Literal, ValidationError | Ecrire et maintenir parsing, conversion, validation et erreurs |
| Avantage | Comportement standard, tests avec fixtures et monkeypatch | Controle precis des regles, moins de dependances possibles |
| Limite | Conventions, versions compatibles, dependances transitives | Plus de code de support et de cas limites a couvrir |

uv et pytest peuvent etre utilises dans les deux architectures. Pydantic n'est pas un framework d'orchestration ; son emploi reste compatible avec une boucle maison.

## ESSENTIEL A APPRENDRE POUR L'ENTRETIEN

### Settings validation ? Validation de configuration

Definition : transformer des entrees externes en parametres types et refuser les valeurs invalides. Role : Settings limite environment et log_level a des valeurs connues avant le demarrage. Pourquoi : eviter une execution avec une configuration incoherente. Automatique : BaseSettings lit les sources et Pydantic valide les Literal, rejette les extras dotenv et leve ValidationError. Sans ces bibliotheques : parser et verifier chaque champ, gerer les erreurs et les priorites a la main.

Question : quelle source gagne si une valeur est dans .env et dans l'environnement ? Reponse : ici, environnement > dotenv > defaut ; les arguments explicites d'initialisation Pydantic auraient une priorite superieure. Le test de priorite le verifie sans appel reseau.

### Dependency locking ? Verrouillage des dependances

Definition : enregistrer les versions resolues et leurs artefacts dans uv.lock. Role : reproduire l'installation Python 3.10. Pourquoi : eviter qu'une nouvelle version incompatible modifie silencieusement le projet. Automatique : uv resout et synchronise ; --locked refuse un lock obsolete. Sans gestionnaire : suivre les dependances transitives et leurs versions manuellement. Ce mecanisme ne vient pas de LangGraph et reste identique avec une boucle maison.

Question : pyproject.toml suffit-il a reproduire exactement l'environnement ? Reponse : ses plages de versions ne figent pas toute la resolution ; uv.lock et la contrainte Python completent cette reproductibilite.

### Unit and integration testing ? Tests unitaires et d'integration

Definition : verifier une regle isolee puis la cooperation de composants. Role : tests Settings, puis lancement reel du module et du script installe. Pourquoi : detecter erreurs de configuration et de packaging. Automatique : pytest collecte les tests, gere les fixtures temporaires, restaure monkeypatch et rapporte les echecs. Sans pytest : construire un runner et l'isolation, ou utiliser unittest de la bibliotheque standard. Aucun framework d'orchestration ne remplace ces tests.

Question : pourquoi isoler .env et l'environnement dans les tests ? Reponse : pour que les secrets et preferences de la machine ne changent pas les resultats ; tmp_path et monkeypatch rendent les cas deterministes.

### src layout ? Organisation du paquet sous src

Definition : separer le paquet installable de la racine du depot. Role : src/agent_smith est construit par hatchling, installe par uv et lance via un entry point. Pourquoi : les tests exercent le paquet installe et evitent les imports accidentels depuis la racine. Automatique : le backend fabrique le paquet et l'installation expose agent-smith. Sans backend : configurer manuellement distribution et chemins, ou choisir un autre backend ; une architecture From Scratch peut conserver exactement cette structure.

Question : pourquoi tester aussi agent-smith --version ? Reponse : un import reussi ne garantit pas que l'entry point declare dans pyproject.toml est correctement installe.


## Phase 2 - comparaison conceptuelle

Les fichiers From Scratch n'ont pas ete inspectes.

| Aspect | LangChain/Gemini | SDK direct |
|---|---|---|
| API | HumanMessage, ChatGoogleGenerativeAI.invoke, AIMessage | Google contents/parts, Models.generate_content, candidates |
| Responsabilite bibliotheque | Conversion messages/reponses et integration fournisseur | Transport et types Google ; conversion applicative a ecrire |
| Responsabilite application | Settings, Protocol ChatProvider, LLMResponse, erreurs, latence et tests | Memes responsabilites applicatives |
| Avantage | Interface de chat reutilisable pour de futurs fournisseurs | Controle direct sur les options SDK |
| Limite | Dependances et conventions supplementaires | Couplage fournisseur et davantage de conversion a maintenir |

Notions d'entretien : Adapter (adaptateur) separe l'application de LangChain ; Protocol (contrat structurel) decrit ask sans imposer d'heritage ; Mock (simulation) remplace les appels externes ; Usage metadata (metadonnees de consommation) doit rester absent si non rapporte. Les frameworks n'inventent ni les compteurs manquants ni une garantie de securite.


## Phase 3 - orchestration

| Aspect | Framework | From Scratch conceptuel |
|---|---|---|
| Technologie | LangGraph StateGraph, add_conditional_edges, compile, invoke | Machine a etats/controle de flux Python personnalise |
| Responsabilite | Planification des noeuds et propagation des mises a jour | Implementer les transitions et la transmission de l etat |
| Avantage | Graphe inspectable, stream des noeuds reellement executes, Mermaid local | Controle direct et moins de dependances |
| Limite | API/semantique de runtime et limite de recursion a comprendre | Plus de controle de flux a maintenir et tester |

Les politiques metier, limites, erreurs et verification AST restent applicatives dans les deux cas. Aucun fichier de l autre projet inspecte.


## ESSENTIEL A APPRENDRE POUR L'ENTRETIEN - Phase 3

### StateGraph - Graphe a etat

Definition : graphe dont les noeuds lisent un etat et retournent des mises a jour. Role : ordonner generation, verification et finalisation. Pourquoi : rendre explicites les parcours et leurs conditions. LangGraph planifie les noeuds et transmet les mises a jour ; sans lui, cette planification serait une machine a etats personnalisee. Question : pourquoi compiler ? Reponse : compile prepare le graphe executable et verifie sa structure ; invoke ou stream l'execute ensuite.

### Conditional edge - Arete conditionnelle

Definition : transition choisie par une fonction de routage. Role : decide_next_step renvoie retry ou finish. Pourquoi : ne corriger que lorsqu'une erreur est observee et que le budget reste disponible. LangGraph execute la branche choisie ; nous ecrivons la politique de decision dans les deux architectures. Question : pourquoi ne pas laisser le LLM choisir l'arret ? Reponse : la limite de deux appels est une regle applicative deterministe, independante de ses sorties.

### Typed state and boundary validation - Etat type et validation aux frontieres

Definition : TypedDict decrit les cles pour le typage, Pydantic controle les valeurs a l'execution. Role : GraphState pour le runtime et AgentState pour les invariants. Pourquoi : concilier mises a jour partielles du graphe et contrats verifiables. LangGraph transmet l'etat mais ne remplace pas nos validations ; sans lui, la meme validation Pydantic peut etre conservee. Question : TypedDict valide-t-il max_llm_calls ? Reponse : non, Field et model_validator dans AgentState le font, et generate_node garde aussi le budget avant l'appel.

### Abstract Syntax Tree - Arbre syntaxique abstrait

Definition : representation structurelle du code apres analyse. Role : ast.parse detecte les erreurs syntaxiques sans executer le programme. Pourquoi : fournir une observation concrete sans sandbox encore disponible. LangGraph ne fait aucune verification automatique du code ; ast appartient a la bibliotheque standard et reste identique From Scratch. Question : une verification AST reussie signifie-t-elle que la fonction est correcte ? Reponse : non, un nom inexistant ou un mauvais algorithme peuvent passer ; le statut est donc unverified, jamais success.
