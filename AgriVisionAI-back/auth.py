from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import tensorflow as tf
import numpy as np
import os
import uuid
import shutil
import uvicorn
import json  # Ajout important
from typing import Dict, List
from datetime import datetime
from pathlib import Path
import requests
# Import des modules internes
from database import get_db, engine
from models import Base, User, Diagnostic
from schemas import (
    UserCreate, UserLogin, Token,
    DiagnosticCreate, DiagnosticHistoryResponse, UserDashboardResponse
)
from security import create_access_token, get_current_user, create_refresh_token, verify_password as verify_password_security, get_password_hash
WEATHER_API_KEY='4048cf8bf28d354845124398c0defe41'

app = FastAPI(
    title="AgriVision AI - Plant Disease Detection API",
    version="2.1.0"
)

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# GLOBALS
# =========================
MODEL = None
CLASS_NAMES = None

# =========================
# RECOMMENDATIONS
# =========================
RECOMMENDATIONS_DB = {
    # POMMES
    "Apple___Apple_scab": {
        "plant": "Pommier",
        "disease_name": "Tavelure du pommier",
        "severity": "medium",
        "description": "Maladie fongique causée par Venturia inaequalis affectant feuilles et fruits",
        "immediate_actions": [
            "Retirer et détruire les feuilles mortes",
            "Appliquer un fongicide au début du printemps",
            "Tailler pour améliorer la circulation d'air"
        ],
        "prevention": "Ramassage des feuilles mortes, variétés résistantes",
        "products": ["Soufre", "Captane", "Myclobutanil"],
        "weather_alert": "Conditions humides et fraîches favorisent la maladie"
    },
    "Apple___Black_rot": {
        "plant": "Pommier",
        "disease_name": "Pourriture noire",
        "severity": "medium",
        "description": "Maladie fongique causée par Botryosphaeria obtusa",
        "immediate_actions": [
            "Retirer les fruits momifiés",
            "Éliminer le bois mort",
            "Appliquer un fongicide pendant la floraison"
        ],
        "prevention": "Taille sanitaire, élimination des débris",
        "products": ["Fongicide au cuivre", "Soufre"],
        "weather_alert": "Temps chaud et humide favorise l'infection"
    },
    "Apple___Cedar_apple_rust": {
        "plant": "Pommier",
        "disease_name": "Rouille du pommier",
        "severity": "low",
        "description": "Maladie causée par Gymnosporangium juniperi-virginianae nécessitant deux hôtes",
        "immediate_actions": [
            "Retirer les feuilles infectées",
            "Appliquer un fongicide au printemps",
            "Éliminer les genévriers à proximité si possible"
        ],
        "prevention": "Planter loin des genévriers, variétés résistantes",
        "products": ["Myclobutanil", "Trifloxystrobine"],
        "weather_alert": "Printemps humide favorise la maladie"
    },
    "Apple___healthy": {
        "plant": "Pommier",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Arbre sain",
        "immediate_actions": ["Continuer les bonnes pratiques culturales"],
        "prevention": "Inspection régulière, fertilisation équilibrée",
        "products": [],
        "weather_alert": ""
    },
    
    # MYRTILLE
    "Blueberry___healthy": {
        "plant": "Myrtille",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Arbuste sain",
        "immediate_actions": ["Maintenir le pH du sol acide"],
        "prevention": "Paillage, irrigation goutte-à-goutte",
        "products": [],
        "weather_alert": ""
    },
    
    # CERISIER
    "Cherry_(including_sour)___Powdery_mildew": {
        "plant": "Cerisier",
        "disease_name": "Oïdium",
        "severity": "low",
        "description": "Maladie fongique formant un feutrage blanc sur les feuilles",
        "immediate_actions": [
            "Tailler pour améliorer la ventilation",
            "Appliquer un fongicide",
            "Retirer les feuilles très infectées"
        ],
        "prevention": "Espacer les plants, éviter l'excès d'azote",
        "products": ["Soufre", "Bicarbonate de potassium"],
        "weather_alert": "Conditions chaudes et sèches avec humidité nocturne"
    },
    "Cherry_(including_sour)___healthy": {
        "plant": "Cerisier",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Arbre sain",
        "immediate_actions": ["Tailler après récolte"],
        "prevention": "Protection contre les oiseaux, irrigation régulière",
        "products": [],
        "weather_alert": ""
    },
    
    # MAÏS
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": {
        "plant": "Maïs",
        "disease_name": "Taches foliaires (Cercospora et Gray leaf spot)",
        "severity": "high",
        "description": "Maladies fongiques causant des taches sur les feuilles",
        "immediate_actions": [
            "Appliquer un fongicide foliaire",
            "Réduire la densité de plantation",
            "Éviter les excès d'azote"
        ],
        "prevention": "Rotation des cultures, résidus de récolte",
        "products": ["Azoxystrobine", "Pyraclostrobine"],
        "weather_alert": "Temps chaud et humide"
    },
    "Corn_(maize)___Common_rust_": {
        "plant": "Maïs",
        "disease_name": "Rouille commune du maïs",
        "severity": "medium",
        "description": "Maladie fongique causée par Puccinia sorghi",
        "immediate_actions": [
            "Appliquer un fongicide si détection précoce",
            "Surveiller la propagation"
        ],
        "prevention": "Variétés résistantes, rotation",
        "products": ["Triazolés", "Strobilurines"],
        "weather_alert": "Nuits fraîches et journées chaudes"
    },
    "Corn_(maize)___Northern_Leaf_Blight": {
        "plant": "Maïs",
        "disease_name": "Brûlure nordique des feuilles",
        "severity": "medium",
        "description": "Maladie fongique causée par Exserohilum turcicum",
        "immediate_actions": [
            "Application de fongicide",
            "Éliminer les résidus infectés"
        ],
        "prevention": "Labour profond, variétés résistantes",
        "products": ["Propiconazole", "Trifloxystrobine"],
        "weather_alert": "Temps frais et humide"
    },
    "Corn_(maize)___healthy": {
        "plant": "Maïs",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Culture saine",
        "immediate_actions": ["Maintenir une fertilisation équilibrée"],
        "prevention": "Rotation, contrôle des adventices",
        "products": [],
        "weather_alert": ""
    },
    
    # VIGNE
    "Grape___Black_rot": {
        "plant": "Vigne",
        "disease_name": "Pourriture noire",
        "severity": "high",
        "description": "Maladie fongique causée par Guignardia bidwellii",
        "immediate_actions": [
            "Retirer et détruire les grappes infectées",
            "Appliquer un fongicide",
            "Tailler pour aérer"
        ],
        "prevention": "Taille hivernale rigoureuse",
        "products": ["Myclobutanil", "Captane"],
        "weather_alert": "Pluies printanières et étés chauds"
    },
    "Grape___Esca_(Black_Measles)": {
        "plant": "Vigne",
        "disease_name": "Esca (Maladie noire)",
        "severity": "high",
        "description": "Maladie complexe du bois de la vigne",
        "immediate_actions": [
            "Tailler et éliminer le bois malade",
            "Protéger les plaies de taille"
        ],
        "prevention": "Désinfection des outils, matériel sain",
        "products": ["Paste cicatrisant"],
        "weather_alert": "Stress hydrique favorise l'expression"
    },
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": {
        "plant": "Vigne",
        "disease_name": "Brûlure des feuilles",
        "severity": "medium",
        "description": "Maladie fongique affectant le feuillage",
        "immediate_actions": [
            "Appliquer un fongicide",
            "Retirer les feuilles très atteintes"
        ],
        "prevention": "Bonne exposition au soleil",
        "products": ["Fongicide au cuivre"],
        "weather_alert": "Étés chauds et humides"
    },
    "Grape___healthy": {
        "plant": "Vigne",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Vigne saine",
        "immediate_actions": ["Continuer les traitements préventifs"],
        "prevention": "Taille adéquate, drainage",
        "products": [],
        "weather_alert": ""
    },
    
    # ORANGER
    "Orange___Haunglongbing_(Citrus_greening)": {
        "plant": "Oranger/Citrus",
        "disease_name": "Huanglongbing (Verdissement des agrumes)",
        "severity": "critical",
        "description": "Maladie bactérienne incurable transmise par psylle",
        "immediate_actions": [
            "Arracher et détruire les arbres symptomatiques",
            "Lutter contre le psylle asiatique",
            "Isoler la zone infectée"
        ],
        "prevention": "Plants certifiés, surveillance du psylle",
        "products": ["Insecticides systémiques"],
        "weather_alert": "Risque accru dans les zones endémiques"
    },
    
    # PÊCHER
    "Peach___Bacterial_spot": {
        "plant": "Pêcher",
        "disease_name": "Taches bactériennes",
        "severity": "medium",
        "description": "Maladie causée par Xanthomonas arboricola pv. pruni",
        "immediate_actions": [
            "Appliquer un traitement cuprique",
            "Tailler les branches infectées"
        ],
        "prevention": "Variétés résistantes, éviter l'irrigation par aspersion",
        "products": ["Cuivre", "Streptomycine"],
        "weather_alert": "Pluies et vents favorisent la dissémination"
    },
    "Peach___healthy": {
        "plant": "Pêcher",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Arbre sain",
        "immediate_actions": ["Tailler en forme de vase ouvert"],
        "prevention": "Protection hivernale, fertilisation adaptée",
        "products": [],
        "weather_alert": ""
    },
    
    # POIVRON
    "Pepper,_bell___Bacterial_spot": {
        "plant": "Poivron",
        "disease_name": "Taches bactériennes",
        "severity": "medium",
        "description": "Maladie causée par Xanthomonas spp.",
        "immediate_actions": [
            "Retirer les plantes très atteintes",
            "Éviter l'arrosage du feuillage",
            "Appliquer un traitement cuprique"
        ],
        "prevention": "Semences saines, rotation longue",
        "products": ["Cuivre", "Mancozèbe"],
        "weather_alert": "Conditions chaudes et humides"
    },
    "Pepper,_bell___healthy": {
        "plant": "Poivron",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Plante saine",
        "immediate_actions": ["Tuteurage si nécessaire"],
        "prevention": "Paillage, irrigation régulière",
        "products": [],
        "weather_alert": ""
    },
    
    # POMME DE TERRE
    "Potato___Early_blight": {
        "plant": "Pomme de terre",
        "disease_name": "Mildiou précoce",
        "severity": "medium",
        "description": "Maladie fongique causée par Alternaria solani",
        "immediate_actions": [
            "Appliquer un fongicide",
            "Éliminer les feuilles infectées"
        ],
        "prevention": "Rotation, plants sains",
        "products": ["Chlorothalonil", "Azoxystrobine"],
        "weather_alert": "Alternance de périodes humides et sèches"
    },
    "Potato___Late_blight": {
        "plant": "Pomme de terre",
        "disease_name": "Mildiou tardif",
        "severity": "high",
        "description": "Maladie dévastatrice causée par Phytophthora infestans",
        "immediate_actions": [
            "Détruire immédiatement les plantes infectées",
            "Appliquer un fongicide systémique",
            "Cesser l'irrigation par aspersion"
        ],
        "prevention": "Variétés résistantes, buttage",
        "products": ["Métalaxyl", "Cymoxanil"],
        "weather_alert": "Conditions fraîches et humides critiques"
    },
    "Potato___healthy": {
        "plant": "Pomme de terre",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Culture saine",
        "immediate_actions": ["Buttage régulier"],
        "prevention": "Rotation de 4 ans, sol bien drainé",
        "products": [],
        "weather_alert": ""
    },
    
    # FRAMBOISE
    "Raspberry___healthy": {
        "plant": "Framboise",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Arbuste sain",
        "immediate_actions": ["Tailler les cannes ayant fructifié"],
        "prevention": "Palissage, aération",
        "products": [],
        "weather_alert": ""
    },
    
    # SOJA
    "Soybean___healthy": {
        "plant": "Soja",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Culture saine",
        "immediate_actions": ["Inoculation avec rhizobium si nécessaire"],
        "prevention": "Rotation, drainage",
        "products": [],
        "weather_alert": ""
    },
    
    # COURGE
    "Squash___Powdery_mildew": {
        "plant": "Courge",
        "disease_name": "Oïdium",
        "severity": "low",
        "description": "Maladie fongique formant un feutrage blanc",
        "immediate_actions": [
            "Appliquer un fongicide",
            "Retirer les feuilles très infectées"
        ],
        "prevention": "Espacement suffisant",
        "products": ["Soufre", "Bicarbonate de potassium"],
        "weather_alert": "Jours chauds et nuits fraîches"
    },
    
    # FRAISE
    "Strawberry___Leaf_scorch": {
        "plant": "Fraise",
        "disease_name": "Brûlure des feuilles",
        "severity": "medium",
        "description": "Maladie fongique causée par Diplocarpon earliana",
        "immediate_actions": [
            "Retirer les feuilles infectées",
            "Appliquer un fongicide"
        ],
        "prevention": "Plants sains, paillage",
        "products": ["Captane", "Myclobutanil"],
        "weather_alert": "Printemps humides"
    },
    "Strawberry___healthy": {
        "plant": "Fraise",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Plante saine",
        "immediate_actions": ["Renouveler la plantation après 3 ans"],
        "prevention": "Paillage plastique, irrigation goutte-à-goutte",
        "products": [],
        "weather_alert": ""
    },
    
    # TOMATE (complété)
    "Tomato___Bacterial_spot": {
        "plant": "Tomate",
        "disease_name": "Taches bactériennes",
        "severity": "medium",
        "description": "Maladie causée par Xanthomonas spp.",
        "immediate_actions": [
            "Retirer les feuilles infectées",
            "Éviter l'arrosage du feuillage",
            "Appliquer un traitement cuprique"
        ],
        "prevention": "Semences traitées, rotation",
        "products": ["Cuivre", "Mancozèbe"],
        "weather_alert": "Conditions chaudes et humides"
    },
    "Tomato___Early_blight": {
        "plant": "Tomate",
        "disease_name": "Mildiou précoce",
        "severity": "medium",
        "description": "Maladie fongique causée par Alternaria solani",
        "immediate_actions": [
            "Retirer les feuilles infectées",
            "Appliquer un fongicide à base de cuivre",
            "Éviter l'arrosage par aspersion"
        ],
        "prevention": "Rotation des cultures, bon espacement",
        "products": ["Fongicide au cuivre", "Chlorothalonil"],
        "weather_alert": "Conditions humides favorisent la propagation"
    },
    "Tomato___Late_blight": {
        "plant": "Tomate",
        "disease_name": "Mildiou tardif",
        "severity": "high",
        "description": "Maladie dévastatrice causée par Phytophthora infestans",
        "immediate_actions": [
            "Retirer et détruire les plantes infectées",
            "Appliquer un fongicide systémique",
            "Isoler les plantes saines"
        ],
        "prevention": "Utiliser des variétés résistantes, bon drainage",
        "products": ["Métalaxyl", "Famoxadone"],
        "weather_alert": "Risque élevé par temps frais et humide"
    },
    "Tomato___Leaf_Mold": {
        "plant": "Tomate",
        "disease_name": "Moisissure des feuilles",
        "severity": "medium",
        "description": "Maladie fongique dans les serres humides",
        "immediate_actions": [
            "Améliorer la ventilation",
            "Réduire l'humidité",
            "Appliquer un fongicide"
        ],
        "prevention": "Contrôle de l'humidité, bonne circulation d'air",
        "products": ["Fongicide à base de soufre"],
        "weather_alert": "Risque élevé en conditions humides"
    },
    "Tomato___Septoria_leaf_spot": {
        "plant": "Tomate",
        "disease_name": "Tache septorienne",
        "severity": "medium",
        "description": "Maladie fongique causée par Septoria lycopersici",
        "immediate_actions": [
            "Retirer les feuilles basses infectées",
            "Appliquer un fongicide",
            "Éviter l'arrosage du feuillage"
        ],
        "prevention": "Rotation des cultures, paillage",
        "products": ["Chlorothalonil", "Mancozèbe"],
        "weather_alert": "Propagation par temps chaud et humide"
    },
    "Tomato___Spider_mites Two-spotted_spider_mite": {
        "plant": "Tomate",
        "disease_name": "Acariens (tétranyque à deux points)",
        "severity": "low",
        "description": "Ravageur suceur causant des décolorations",
        "immediate_actions": [
            "Appliquez un acaricide",
            "Augmentez l'humidité",
            "Retirez les feuilles gravement atteintes"
        ],
        "prevention": "Surveillance régulière, plantes compagnes répulsives",
        "products": ["Savon insecticide", "Huile de neem", "Acaricides spécifiques"],
        "weather_alert": "Conditions chaudes et sèches favorisent les infestations"
    },
    "Tomato___Target_Spot": {
        "plant": "Tomate",
        "disease_name": "Tache cible",
        "severity": "medium",
        "description": "Maladie fongique causée par Corynespora cassiicola",
        "immediate_actions": [
            "Retirer les feuilles infectées",
            "Appliquer un fongicide",
            "Améliorer la circulation d'air"
        ],
        "prevention": "Rotation, espacement adéquat",
        "products": ["Chlorothalonil", "Azoxystrobine"],
        "weather_alert": "Conditions humides et chaudes"
    },
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": {
        "plant": "Tomate",
        "disease_name": "Virus de l'enroulement jaune de la tomate",
        "severity": "high",
        "description": "Virus transmis par l'aleurode Bemisia tabaci",
        "immediate_actions": [
            "Arracher et détruire les plantes infectées",
            "Lutter contre les aleurodes",
            "Planter des barrières de plantes répulsives"
        ],
        "prevention": "Plants sains, filets anti-insectes",
        "products": ["Insecticides systémiques"],
        "weather_alert": "Risque accru en présence d'aleurodes"
    },
    "Tomato___Tomato_mosaic_virus": {
        "plant": "Tomate",
        "disease_name": "Virus de la mosaïque de la tomate",
        "severity": "medium",
        "description": "Virus très contagieux affectant la croissance",
        "immediate_actions": [
            "Détruire les plantes symptomatiques",
            "Désinfecter les outils",
            "Éviter de fumer près des plants"
        ],
        "prevention": "Résistance génétique, hygiène stricte",
        "products": ["Aucun traitement curatif"],
        "weather_alert": "Transmission mécanique facilitée par temps sec"
    },
    "Tomato___healthy": {
        "plant": "Tomate",
        "disease_name": "Aucune maladie détectée",
        "severity": "Aucune",
        "description": "Plante saine",
        "immediate_actions": ["Continuer les bonnes pratiques"],
        "prevention": "Surveillance régulière",
        "products": [],
        "weather_alert": ""
    }
}

def recommend(predicted_class: str, confidence: float) -> Dict:
    if confidence < 0.4:
        return {
            "status": "low_confidence",
            "message": "Confiance trop faible, reprendre une photo",
            "confidence": confidence,
            "plant": "Inconnu",
            "disease_name": "Indéterminé",
            "severity": "low",
            "description": "",
            "immediate_actions": [],
            "prevention": "",
            "products": [],
            "weather_alert": ""
        }

    if predicted_class in RECOMMENDATIONS_DB:
        rec = RECOMMENDATIONS_DB[predicted_class].copy()
        rec["confidence"] = confidence
        return rec

    return {
        "plant": "Inconnue",
        "disease_name": predicted_class,
        "severity": "Inconnue",
        "confidence": confidence,
        "description": "Classe non documentée",
        "immediate_actions": [],
        "prevention": "",
        "products": [],
        "weather_alert": ""
    }

# =========================
# LOAD MODEL + CLASSES
# =========================
def load_model():
    global MODEL, CLASS_NAMES
    try:
        MODEL = tf.keras.models.load_model("./model_plant/trained_plant_disease_model.keras")
        print("✅ Modèle chargé avec succès")
        
        # Créer un dataset pour obtenir les classes
        if os.path.exists("./model_plant/train"):
            training_set = tf.keras.utils.image_dataset_from_directory(
                "./model_plant/train",
                labels="inferred",
                label_mode="categorical",
                image_size=(128, 128),
                batch_size=32,
                shuffle=False
            )
            CLASS_NAMES = training_set.class_names
        else:
            # Classes par défaut si le dossier train n'existe pas
            CLASS_NAMES = ['Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy', 'Blueberry___healthy', 'Cherry_(including_sour)___Powdery_mildew', 'Cherry_(including_sour)___healthy', 'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot', 'Corn_(maize)___Common_rust_', 'Corn_(maize)___Northern_Leaf_Blight', 'Corn_(maize)___healthy', 'Grape___Black_rot', 'Grape___Esca_(Black_Measles)', 'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)', 'Grape___healthy', 'Orange___Haunglongbing_(Citrus_greening)', 'Peach___Bacterial_spot', 'Peach___healthy', 'Pepper,_bell___Bacterial_spot', 'Pepper,_bell___healthy', 'Potato___Early_blight', 'Potato___Late_blight', 'Potato___healthy', 'Raspberry___healthy', 'Soybean___healthy', 'Squash___Powdery_mildew', 'Strawberry___Leaf_scorch', 'Strawberry___healthy', 'Tomato___Bacterial_spot', 'Tomato___Early_blight', 'Tomato___Late_blight', 'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot', 'Tomato___Spider_mites Two-spotted_spider_mite', 'Tomato___Target_Spot', 'Tomato___Tomato_Yellow_Leaf_Curl_Virus', 'Tomato___Tomato_mosaic_virus', 'Tomato___healthy']
        print(f"📚 Classes chargées ({len(CLASS_NAMES)}): {CLASS_NAMES[:5]}...")
        
    except Exception as e:
        print(f"❌ Erreur lors du chargement du modèle: {e}")
        # Classes par défaut pour le développement
        CLASS_NAMES = ['Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy', 'Blueberry___healthy', 'Cherry_(including_sour)___Powdery_mildew', 'Cherry_(including_sour)___healthy', 'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot', 'Corn_(maize)___Common_rust_', 'Corn_(maize)___Northern_Leaf_Blight', 'Corn_(maize)___healthy', 'Grape___Black_rot', 'Grape___Esca_(Black_Measles)', 'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)', 'Grape___healthy', 'Orange___Haunglongbing_(Citrus_greening)', 'Peach___Bacterial_spot', 'Peach___healthy', 'Pepper,_bell___Bacterial_spot', 'Pepper,_bell___healthy', 'Potato___Early_blight', 'Potato___Late_blight', 'Potato___healthy', 'Raspberry___healthy', 'Soybean___healthy', 'Squash___Powdery_mildew', 'Strawberry___Leaf_scorch', 'Strawberry___healthy', 'Tomato___Bacterial_spot', 'Tomato___Early_blight', 'Tomato___Late_blight', 'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot', 'Tomato___Spider_mites Two-spotted_spider_mite', 'Tomato___Target_Spot', 'Tomato___Tomato_Yellow_Leaf_Curl_Virus', 'Tomato___Tomato_mosaic_virus', 'Tomato___healthy']

# =========================
# PREPROCESS
# =========================
def preprocess_image_tf(image_path: str) -> np.ndarray:
    image = tf.keras.preprocessing.image.load_img(
        image_path,
        target_size=(128, 128)
    )
    input_arr = tf.keras.preprocessing.image.img_to_array(image)
    input_arr = np.array([input_arr])  # batch
    return input_arr

# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    # Créer les tables de la base de données
    Base.metadata.create_all(bind=engine)
    
    # Charger le modèle
    load_model()
    
    # Créer le dossier des uploads
    os.makedirs("uploads/diagnostics", exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    print("✅ Application démarrée avec succès")

# =========================
# ROOT ENDPOINT
# =========================
@app.get("/")
async def root():
    return {
        "service": "AgriVision AI",
        "status": "running",
        "model_loaded": MODEL is not None,
        "version": "2.1.0"
    }

# =========================
# ENDPOINTS - AUTH
# =========================
@app.post("/auth/register", status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Inscription d'un nouvel utilisateur"""
    # Vérifier si l'email existe déjà
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email déjà existant")

    # Créer l'utilisateur
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Utilisateur créé avec succès",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email
        }
    }

@app.post("/auth/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    """Connexion utilisateur"""
    db_user = db.query(User).filter(User.email == user.email).first()
    
    if not db_user or not verify_password_security(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Identifiants invalides"
        )

    # Créer les deux tokens
    access_token = create_access_token(data={"sub": str(db_user.id)})
    refresh_token = create_refresh_token(data={"sub": str(db_user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 1800,  # 30 minutes en secondes
        "user": {
            "id": db_user.id,
            "email": db_user.email
        }
    }

# =========================
# ENDPOINTS - PREDICTION (CORRIGÉ)
# =========================
@app.post("/predict")
async def predict(
    file: UploadFile = File(...), 
    current_user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """Endpoint de prédiction avec sauvegarde automatique du diagnostic"""
    
    print(f"📥 Prédiction demandée par l'utilisateur: {current_user['user_id']}")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="Fichier manquant")

    # Vérifier l'extension du fichier
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
    file_extension = os.path.splitext(file.filename)[1]
    if file_extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Format de fichier non supporté. Utilisez JPG ou PNG")

    # Générer des noms de fichiers uniques
    temp_filename = f"temp_{uuid.uuid4()}.jpg"
    permanent_filename = f"diag_{uuid.uuid4()}{file_extension}"
    temp_path = os.path.join("temp", temp_filename)
    permanent_path = os.path.join("uploads/diagnostics", permanent_filename)
    
    try:
        # 1️⃣ Sauvegarde temporaire pour traitement
        print(f"💾 Sauvegarde temporaire: {temp_path}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2️⃣ Prétraitement
        print("🔄 Prétraitement de l'image...")
        input_arr = preprocess_image_tf(temp_path)

        # 3️⃣ Prédiction
        print("🤖 Exécution de la prédiction...")
        predictions = MODEL.predict(input_arr, verbose=0)
        idx = int(np.argmax(predictions[0]))
        predicted_class = CLASS_NAMES[idx]
        confidence_score = float(predictions[0][idx])
        
        print(f"📊 Résultat: {predicted_class} (confiance: {confidence_score:.2%})")

        # 4️⃣ Recommandation
        rec = recommend(predicted_class, confidence_score)
        
        # 5️⃣ Sauvegarde permanente de l'image
        shutil.copy(temp_path, permanent_path)
        print(f"📁 Image sauvegardée: {permanent_path}")
        
        # 6️⃣ Construire les données du diagnostic
        plant_name = rec.get("plant", "Inconnu")
        disease_name = rec.get("disease_name", "Indéterminé")
        severity_level = rec.get("severity", "low")
        
        # 7️⃣ CORRECTION IMPORTANTE : Convertir les recommandations en JSON string
        recommendations_list = rec.get("immediate_actions", [])
        recommendations_json = json.dumps(recommendations_list, ensure_ascii=False)
        
        print(f"📝 Diagnostic: {plant_name} - {disease_name}")
        print(f"⚠️  Sévérité: {severity_level}")
        print(f"📋 Recommandations JSON: {recommendations_json}")
        
        # 8️⃣ Sauvegarder le diagnostic dans la base de données
        new_diagnostic = Diagnostic(
            user_id=current_user["user_id"],
            plant=plant_name,
            disease=disease_name,
            severity=severity_level,
            confidence=confidence_score,
            image_path=permanent_path,
            recommendations=recommendations_json,  # JSON string, pas une liste !
            date=datetime.utcnow()
        )
        
        db.add(new_diagnostic)
        db.commit()
        db.refresh(new_diagnostic)
        
        print(f"✅ Diagnostic sauvegardé avec ID: {new_diagnostic.id}")

        # 9️⃣ Retourner la réponse complète
        response = {
            "success": True,
            "plant": plant_name,
            "disease": disease_name,
            "severity": severity_level,
            "confidence": round(confidence_score * 100, 2),
            "description": rec.get("description", ""),
            "recommendations": recommendations_list,  # Liste Python pour la réponse API
            "prevention": rec.get("prevention", ""),
            "products": rec.get("products", []),
            "weather_alert": rec.get("weather_alert", ""),
            "raw_class": predicted_class,
            "filename": file.filename,
            "diagnostic_id": new_diagnostic.id,
            "diagnostic_date": new_diagnostic.date.strftime("%d/%m/%Y %H:%M"),
            "image_url": f"/uploads/diagnostics/{permanent_filename}"
        }
        
        print("✅ Prédiction terminée avec succès")
        return response

    except Exception as e:
        print(f"❌ Erreur lors de la prédiction: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la prédiction: {str(e)}")

    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print(f"🧹 Fichier temporaire nettoyé: {temp_path}")

# =========================
# ENDPOINTS - DIAGNOSTICS
# =========================
@app.post("/diagnostics", response_model=DiagnosticHistoryResponse)
def save_diagnostic(
    diagnostic: DiagnosticCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sauvegarder un nouveau diagnostic (alternative manuelle)"""
    # Convertir les recommandations en JSON pour la base de données
    recommendations_json = json.dumps(diagnostic.recommendations, ensure_ascii=False)
    
    new_diagnostic = Diagnostic(
        user_id=current_user["user_id"],
        plant=diagnostic.plant,
        disease=diagnostic.disease,
        severity=diagnostic.severity,
        confidence=diagnostic.confidence,
        image_path=diagnostic.image_path,
        recommendations=recommendations_json,  # JSON string
        date=datetime.utcnow()
    )
    
    db.add(new_diagnostic)
    db.commit()
    db.refresh(new_diagnostic)
    
    return DiagnosticHistoryResponse(
        id=new_diagnostic.id,
        date=new_diagnostic.date.strftime("%d/%m/%Y %H:%M"),
        plant=new_diagnostic.plant,
        disease=new_diagnostic.disease,
        severity=new_diagnostic.severity,
        confidence=int(new_diagnostic.confidence * 100)
    )

@app.get("/diagnostics", response_model=List[DiagnosticHistoryResponse])
def get_user_diagnostics(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Récupérer l'historique des diagnostics d'un utilisateur"""
    diagnostics = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"]
    ).order_by(Diagnostic.date.desc()).limit(limit).all()
    
    return [
        DiagnosticHistoryResponse(
            id=diag.id,
            date=diag.date.strftime("%d/%m/%Y %H:%M") if diag.date else "",
            plant=diag.plant,
            disease=diag.disease,
            severity=diag.severity,
            confidence=int(diag.confidence * 100)
        )
        for diag in diagnostics
    ]

@app.get("/diagnostics/stats")
def get_diagnostic_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Statistiques des diagnostics"""
    total = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"]
    ).count()
    
    high_confidence = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"],
        Diagnostic.confidence >= 0.8
    ).count()
    
    success_rate = (high_confidence / total * 100) if total > 0 else 0
    
    return {
        "totalDiagnostics": total,
        "highConfidence": high_confidence,
        "successRate": round(success_rate, 2)
    }

# =========================
# ENDPOINTS - DASHBOARD
# =========================
@app.get("/auth/dashboard", response_model=UserDashboardResponse)
def get_user_dashboard(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Tableau de bord complet de l'utilisateur"""
    recent_diagnostics = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"]
    ).order_by(Diagnostic.date.desc()).limit(1).all()
    
    total_diagnostics = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"]
    ).count()
    
    high_confidence = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"],
        Diagnostic.confidence >= 0.8
    ).count()
    
    success_rate = (high_confidence / total_diagnostics * 100) if total_diagnostics > 0 else 0
    
    # Retourner le tableau de bord
    print("📊 Récupération du tableau de bord utilisateur")
    print(f"👤 Utilisateur ID: {current_user['user_id']}")
    return UserDashboardResponse(
        user_info={
            "id": current_user["user_id"],
            "username": current_user["username"],
            "email": current_user["email"]
        },
        recentDiagnostics=[
            DiagnosticHistoryResponse(
                id=diag.id,
                date=diag.date.strftime("%d/%m/%Y %H:%M") if diag.date else "",
                plant=diag.plant,
                disease=diag.disease,
                severity=diag.severity,
                confidence=int(diag.confidence * 100)
            )
            for diag in recent_diagnostics
        ],
        totalDiagnostics=total_diagnostics,
        successRate=round(success_rate, 2)
    )

# =========================
#weather
# Coordonnées Safi
SAFI_LAT = 32.299
SAFI_LON = -9.237


@app.get("/weather")
async def get_weather():
    """
    Météo actuelle pour Safi via Open-Meteo (gratuit, sans clé API)
    """
    try:
        print("🌤️  Requête météo pour Safi")

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": SAFI_LAT,
            "longitude": SAFI_LON,
            "current_weather": True
        }

        response = requests.get(url, params=params, timeout=10)
        print(f"📡 Statut HTTP: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            weather = data["current_weather"]

            return {
                "city": "Safi",
                "temperature": weather["temperature"],
                "windspeed": weather["windspeed"],
                "winddirection": weather["winddirection"],
                "time": weather["time"],
                "unit": "°C"
            }

        return {
            "city": "Safi",
            "temperature": 24.0,
            "description": "Erreur service météo",
            "error": f"HTTP {response.status_code}"
        }

    except Exception as e:
        return {
            "city": "Safi",
            "temperature": 24.0,
            "description": "Erreur inattendue",
            "error": str(e)
        }
# ENDPOINTS - SUPPRESSION
# =========================
@app.delete("/diagnostics/{diagnostic_id}")
def delete_diagnostic(
    diagnostic_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Supprimer un diagnostic"""
    diagnostic = db.query(Diagnostic).filter(
        Diagnostic.user_id == current_user["user_id"],
        Diagnostic.id == diagnostic_id
    ).first()
    
    if not diagnostic:
        raise HTTPException(status_code=404, detail="Diagnostic non trouvé")
    
    # Supprimer également le fichier image
    if diagnostic.image_path and os.path.exists(diagnostic.image_path):
        os.remove(diagnostic.image_path)
    
    db.delete(diagnostic)
    db.commit()
    
    return {"message": "Diagnostic supprimé"}

# =========================
# HEALTH CHECK
# =========================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "model_loaded": MODEL is not None,
        "model_classes": len(CLASS_NAMES) if CLASS_NAMES else 0,
        "timestamp": datetime.utcnow().isoformat()
    }

# =========================
# DEBUG ENDPOINTS (optionnels)
# =========================
@app.get("/debug/db-structure")
async def debug_db_structure(db: Session = Depends(get_db)):
    """Endpoint de débogage pour vérifier la structure de la base"""
    from sqlalchemy import inspect
    
    inspector = inspect(db.get_bind())
    
    tables = inspector.get_table_names()
    table_info = {}
    
    for table in tables:
        columns = inspector.get_columns(table)
        table_info[table] = [
            {
                'name': col['name'],
                'type': str(col['type']),
                'nullable': col.get('nullable', True)
            }
            for col in columns
        ]
    
    # Vérifier les diagnostics existants
    diagnostics = db.query(Diagnostic).limit(5).all()
    diagnostics_data = []
    
    for diag in diagnostics:
        diagnostics_data.append({
            'id': diag.id,
            'plant': diag.plant,
            'disease': diag.disease,
            'recommendations': diag.recommendations,
            'recommendations_type': type(diag.recommendations).__name__
        })
    
    return {
        'tables': table_info,
        'sample_diagnostics': diagnostics_data,
        'total_diagnostics': db.query(Diagnostic).count()
    }

@app.get("/debug/test-insert")
async def debug_test_insert(db: Session = Depends(get_db)):
    """Test d'insertion simple"""
    test_diagnostic = Diagnostic(
        user_id=1,
        plant="Tomate Test",
        disease="Maladie Test",
        severity="low",
        confidence=0.95,
        image_path="test.jpg",
        recommendations=json.dumps(["Recommandation 1", "Recommandation 2"]),
        date=datetime.utcnow()
    )
    
    db.add(test_diagnostic)
    db.commit()
    db.refresh(test_diagnostic)
    
    return {
        'success': True,
        'id': test_diagnostic.id,
        'recommendations': test_diagnostic.recommendations
    }

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )