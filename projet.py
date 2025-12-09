#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GMQ710 - PROJET FINAL : RECONSTRUCTION 3D CAMPUS UDE S
Objectif : Générer une scène CityJSON (Bâtiments + Végétation) sur une zone précise.

Améliorations :
1. Découpage strict des données (Raster & Vecteur) selon les coordonnées du campus.
2. Utilisation de Logging pour le suivi.
3. Optimisation automatique de la densité de végétation.
"""

import os
import logging
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.features import rasterize
from shapely.geometry import Polygon

# ------------------------------------------------------------------------------
# 1. CONFIGURATION
# ------------------------------------------------------------------------------
BASE_PATH = r"E:\Cours_Université_de_Sherbrooke\Cours_Maîtrise_1\Automne_2025\gmq710\projet"

FILES = {
    "dsm": "dsm_1m_utm19_w_22_102.tif",
    "dtm": "dtm_1m_utm19_w_22_102.tif",
    "osm": "buildings_sherbrooke_osm.geojson",
    "output": "scene_campus_final.city.json"
}

# Coordonnées du Campus (Lat/Lon - WGS84)
# Ordre : Haut-Gauche -> Haut-Droite -> Bas-Droite -> Bas-Gauche
COORDS_CAMPUS = [
    (-71.933067, 45.381338),
    (-71.924435, 45.381351),
    (-71.924429, 45.377744),
    (-71.932799, 45.377691)
]

PARAMS = {
    "epsg": 26919,            # Projection UTM 19N
    "min_h_bat": 3.0,         # Hauteur min bâtiments
    "min_h_veg": 2.5,         # Hauteur min arbres
    "max_trees": 150000       # Sécurité performance QGIS
}

# Configuration du Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 2. CLASSE UTILITAIRE CITYJSON
# ------------------------------------------------------------------------------
class CityJSONWriter:
    def __init__(self):
        self.vertices = []
        self.lookup = {}
        self.city_objects = {}

    def add_vertex(self, x, y, z):
        # Arrondi au cm pour optimiser
        pt = (round(x, 2), round(y, 2), round(z, 2))
        if pt in self.lookup: return self.lookup[pt]
        idx = len(self.vertices)
        self.vertices.append(pt)
        self.lookup[pt] = idx
        return idx

    def add_object(self, obj_id, obj_type, geometry, attributes):
        self.city_objects[obj_id] = {
            "type": obj_type,
            "attributes": attributes,
            "geometry": [geometry]
        }

    def save(self, path, crs_epsg, bbox):
        scale = 0.01
        vertices_int = [[int(v[0]/scale), int(v[1]/scale), int(v[2]/scale)] for v in self.vertices]
        
        data = {
            "type": "CityJSON",
            "version": "2.0",
            "metadata": {
                "referenceSystem": f"urn:ogc:def:crs:EPSG::{crs_epsg}",
                "geographicalExtent": bbox
            },
            "transform": {"scale": [scale, scale, scale], "translate": [0, 0, 0]},
            "CityObjects": self.city_objects,
            "vertices": vertices_int
        }
        try:
            with open(path, 'w') as f: json.dump(data, f)
            logger.info(f"Fichier sauvegardé : {path}")
        except Exception as e:
            logger.error(f"Erreur écriture : {e}")

# ------------------------------------------------------------------------------
# 3. FONCTIONS MÉTIER
# ------------------------------------------------------------------------------

def preparer_zone_etude(coords, target_crs):
    """Crée le polygone de découpe et le projette."""
    logger.info("Configuration de la zone d'étude (Campus)...")
    poly_wgs84 = Polygon(coords)
    gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[poly_wgs84])
    gdf_proj = gdf.to_crs(f"EPSG:{target_crs}")
    return gdf_proj.geometry[0]

def charger_et_decouper_raster(path, mask_poly):
    """Charge un raster et le découpe selon le polygone."""
    with rasterio.open(path) as src:
        out_image, out_transform = mask(src, [mask_poly], crop=True, nodata=0)
        return out_image[0], out_transform

def creer_geometrie_batiment(polygon, z_min, height, writer):
    """Crée un solide LOD1."""
    z_max = z_min + height
    boundaries = []
    try:
        coords = list(polygon.exterior.coords)
        if coords[0] == coords[-1]: coords.pop()
        
        floor = [writer.add_vertex(x, y, z_min) for x, y in reversed(coords)]
        roof = [writer.add_vertex(x, y, z_max) for x, y in coords]
        boundaries.append([floor])
        boundaries.append([roof])
        
        for i in range(len(coords)):
            p1 = coords[i]
            p2 = coords[(i+1)%len(coords)]
            idx1 = writer.add_vertex(p1[0], p1[1], z_min)
            idx2 = writer.add_vertex(p2[0], p2[1], z_min)
            idx3 = writer.add_vertex(p2[0], p2[1], z_max)
            idx4 = writer.add_vertex(p1[0], p1[1], z_max)
            boundaries.append([[idx1, idx2, idx3, idx4]])
        return {"type": "Solid", "lod": "1", "boundaries": [boundaries]}
    except: return None

def creer_geometrie_arbre(x, y, z_base, height, writer, width=1.0):
    """Crée un cube simple pour représenter un arbre."""
    w = width / 2
    z_top = z_base + height
    corners = [(x-w, y-w), (x+w, y-w), (x+w, y+w), (x-w, y+w)]
    boundaries = []
    
    # Sol et Toit
    boundaries.append([[writer.add_vertex(px, py, z_base) for px, py in reversed(corners)]])
    boundaries.append([[writer.add_vertex(px, py, z_top) for px, py in corners]])
    
    # Côtés
    for i in range(4):
        p1 = corners[i]
        p2 = corners[(i+1)%4]
        pts = [
            writer.add_vertex(p1[0], p1[1], z_base),
            writer.add_vertex(p2[0], p2[1], z_base),
            writer.add_vertex(p2[0], p2[1], z_top),
            writer.add_vertex(p1[0], p1[1], z_top)
        ]
        boundaries.append([pts])
    return {"type": "Solid", "lod": "1", "boundaries": [boundaries]}

# ------------------------------------------------------------------------------
# 4. PIPELINE PRINCIPAL
# ------------------------------------------------------------------------------

def run():
    logger.info("=== DÉMARRAGE PIPELINE 3D CAMPUS ===")
    
    # 1. Zone d'étude
    zone_poly = preparer_zone_etude(COORDS_CAMPUS, PARAMS["epsg"])
    
    # 2. Chargement & Découpage Rasters
    dsm_p = os.path.join(BASE_PATH, FILES["dsm"])
    dtm_p = os.path.join(BASE_PATH, FILES["dtm"])
    
    logger.info("Lecture et découpage des rasters (MNS/MNT)...")
    dsm, transform = charger_et_decouper_raster(dsm_p, zone_poly)
    dtm, _ = charger_et_decouper_raster(dtm_p, zone_poly)
    
    # Calcul nDSM (Hauteur relative)
    ndsm = dsm - dtm
    ndsm[ndsm < 0] = 0
    
    # 3. Chargement & Découpage Bâtiments
    osm_p = os.path.join(BASE_PATH, FILES["osm"])
    logger.info("Lecture et découpage des bâtiments OSM...")
    buildings = gpd.read_file(osm_p).to_crs(f"EPSG:{PARAMS['epsg']}")
    
    # Filtre spatial : on ne garde que ce qui intersecte le campus
    buildings = buildings[buildings.geometry.intersects(zone_poly)]
    
    # 4. Traitement Bâtiments
    writer = CityJSONWriter()
    mask_bat = np.zeros(dsm.shape, dtype='uint8')
    count_bat = 0
    
    for idx, row in buildings.iterrows():
        geom = row.geometry
        if geom.is_empty: continue
        
        try:
            # On crée un masque raster local pour le bâtiment pour lire les hauteurs
            mask_b = rasterize([geom], out_shape=dsm.shape, transform=transform, fill=0, default_value=1, dtype='uint8')
            mask_bat = np.maximum(mask_bat, mask_b) # Mise à jour masque global (pour éviter arbres sur toits)
            
            h_vals = ndsm[mask_b == 1]
            if h_vals.size == 0: continue
            
            h_bat = float(h_vals.max())
            z_base = float(dtm[mask_b == 1].min())
            
            if h_bat >= PARAMS["min_h_bat"]:
                # Simplification légère pour alléger le JSON
                simple_geom = geom.simplify(0.5, preserve_topology=True)
                polys = [simple_geom] if simple_geom.geom_type == 'Polygon' else simple_geom.geoms
                
                for i, poly in enumerate(polys):
                    g = creer_geometrie_batiment(poly, z_base, h_bat, writer)
                    if g:
                        obj_id = f"Bat_{idx}_{i}"
                        writer.add_object(obj_id, "Building", g, {"measuredHeight": round(h_bat, 2)})
                        count_bat += 1
        except: pass
        
    logger.info(f" -> {count_bat} bâtiments générés sur le campus.")

    # 5. Traitement Végétation
    logger.info("Analyse de la végétation...")
    veg_mask = (ndsm > PARAMS["min_h_veg"]) & (mask_bat == 0) & (dsm > 0) # dsm>0 évite les bords noirs
    rows, cols = np.where(veg_mask)
    
    total_pixels = len(rows)
    logger.info(f" -> Pixels potentiels : {total_pixels}")
    
    # Calcul automatique du "Pas" (Step) pour ne pas tuer QGIS
    step = 1
    if total_pixels > PARAMS["max_trees"]:
        step = int(np.ceil(total_pixels / PARAMS["max_trees"]))
        logger.warning(f" -> Densité élevée. Application d'un filtre : 1 arbre tous les {step} pixels.")
    
    rows, cols = rows[::step], cols[::step]
    
    # Ajustement visuel de la largeur de l'arbre si on en saute beaucoup
    tree_width = 1.0 + (step * 0.5) 
    
    count_tree = 0
    xs, ys = rasterio.transform.xy(transform, rows, cols, offset='center')
    
    for x, y, r, c in zip(xs, ys, rows, cols):
        h = float(ndsm[r, c])
        z = float(dtm[r, c])
        
        g = creer_geometrie_arbre(x, y, z, h, writer, width=tree_width)
        writer.add_object(f"Veg_{count_tree}", "SolitaryVegetationObject", g, {"height": round(h, 1)})
        count_tree += 1
        
    logger.info(f" -> {count_tree} arbres générés.")

    # 6. Export
    bounds = zone_poly.bounds
    bbox = [bounds[0], bounds[1], float(dtm.min()), bounds[2], bounds[3], float(dsm.max())]
    
    out_path = os.path.join(BASE_PATH, FILES["output"])
    writer.save(out_path, PARAMS["epsg"], bbox)
    
    logger.info("=== TRAITEMENT TERMINÉ AVEC SUCCÈS ===")

if __name__ == "__main__":
    run()