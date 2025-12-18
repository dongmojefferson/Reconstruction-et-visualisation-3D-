# GMQ710 – Reconstruction 3D Sémantique du Campus de l'UdeS (CityJSON)

## Objectifs
Ce projet a permis de développer un pipeline de traitement géospatial automatisé en Python pour produire une maquette numérique 3D (Jumeau Numérique) du campus de l'Université de Sherbrooke.

L'objectif principal est la fusion de données hétérogènes pour générer une scène 3D sémantique :
* **Bâtiments** : Calcul de la hauteur (LoD1) par analyse zonale et extrusion.
* **Végétation** : Identification de la canopée et des arbres isolés.
* **Optimisation** : Exportation hybride (CityJSON/GeoJSON) pour garantir la fluidité de l'affichage 3D.

## Accès aux données
Pour reproduire les résultats de ce projet, les données sources (MNS, MNT et empreintes OSM) sont disponibles en téléchargement via le lien suivant :
👉 **[Télécharger les données du projet (Google Drive)](https://drive.google.com/file/d/1OFyiVwdWz9q5wFBQQ2z7WoqJ3OOoW_K5/view?usp=sharing)**

## Données utilisées
| Source | Type | Format | Utilité |
| :--- | :--- | :--- | :--- |
| **MNEHR (MNS)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Surface (altitude des sommets). |
| **MNEHR (MNT)** | Raster (1 m) | GeoTIFF | Modèle Numérique de Terrain (altitude du sol nu). |
| **OpenStreetMap** | Vecteur | GeoJSON | Empreintes 2D des bâtiments pour l'extrusion. |

## Approche / Méthodologie finale
L'approche algorithmique suit ces étapes clés :
1. **Prétraitement** : Reprojection uniforme en NAD83 / UTM Zone 19N (EPSG:26919).
2. **Calcul du nDSM** : Génération du modèle de hauteur normalisé ($MNS - MNT$).
3. **Modélisation des Bâtis (CityJSON 2.0)** : 
    - Analyse zonale (percentile 95) pour une extraction de hauteur robuste.
    - Gestion des **MultiPolygons** pour assurer la validité géométrique des solides.
    - Exportation de 45 bâtiments en format `Solid`.
4. **Extraction de la Végétation (GeoJSON)** : 
    - Filtrage des pixels > 2.5m situés hors des empreintes bâties.
    - **Dédoublonnage spatial** (distance min. 3.5m) pour isoler les individus.
    - Exportation de 3 264 arbres en points 3D (X, Y, Z_sol + attribut hauteur).

## Validation et Tests
Pour garantir la robustesse du pipeline, un script de contrôle (`test_pipeline.py`) est utilisé pour :
* **Valider les chemins** et l'existence des fichiers volumineux.
* **Vérifier le système de coordonnées (CRS)** : Alerte si l'étiquette EPSG est absente tout en validant la structure des données UTM.
* **Tester l'importation** des modules et la configuration (seuils de hauteur, coordonnées du campus).

## Outils et bibliothèques
* **Langage** : Python 3.8+
* **Bibliothèques** : `rasterio`, `geopandas`, `shapely`, `fiona`, `numpy`, `json`.

## Répartition des tâches
* **Jefferson Dongmo Somtsi** : Structure CityJSON, gestion des géométries complexes, résolution des conflits Git et intégration des tests unitaires.
* **Qarek Mbengmo Donfack** : Logique d'analyse spatiale (nDSM), statistiques zonales et filtrage algorithmique de la végétation.

## Questions résolues
**Optimisation du rendu** : Le problème de performance a été résolu par une exportation hybride. Les bâtiments sont en CityJSON pour la richesse sémantique, tandis que la végétation est en GeoJSON. Cela permet à QGIS d'utiliser la symbologie 3D native (instancing) pour afficher les milliers d'arbres de manière fluide.