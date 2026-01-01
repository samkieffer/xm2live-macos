#!/usr/bin/env python3
"""
Script pour embarquer le template minimal dans le code Python
en tant que constante base64
"""

import base64
import os

def embed_template(template_path, output_path):
    """Lit le template .als et génère du code Python avec base64"""

    print(f"📖 Lecture du template...")
    print(f"   {template_path}")

    with open(template_path, 'rb') as f:
        template_bytes = f.read()

    # Encoder en base64
    print(f"\n🔐 Encodage en base64...")
    template_b64 = base64.b64encode(template_bytes).decode('ascii')

    # Couper en lignes de 80 caractères pour lisibilité
    lines = [template_b64[i:i+80] for i in range(0, len(template_b64), 80)]

    print(f"   {len(template_bytes)} bytes → {len(template_b64)} chars base64")
    print(f"   {len(lines)} lignes de code Python")

    # Générer le code Python
    python_code = '''#!/usr/bin/env python3
"""
Template Ableton Live minimal (1 piste MIDI + Sampler)
Généré automatiquement depuis template_minimal_1track.als
"""

import base64
import gzip
from lxml import etree
from io import BytesIO

# Template minimal embarqué (base64 gzip)
MINIMAL_TEMPLATE_BASE64 = """\\
'''

    python_code += '\\\n'.join(lines)

    python_code += '''
"""

def get_minimal_template():
    """
    Retourne le template minimal sous forme d'arbre ElementTree

    Returns:
        etree._ElementTree: Template Ableton avec 1 MidiTrack
    """
    # Décoder base64
    template_gzip = base64.b64decode(MINIMAL_TEMPLATE_BASE64)

    # Décompresser gzip
    template_xml = gzip.decompress(template_gzip)

    # Parser XML
    tree = etree.parse(BytesIO(template_xml))

    return tree

def get_minimal_template_root():
    """
    Retourne la racine du template minimal

    Returns:
        etree._Element: Root element du template
    """
    tree = get_minimal_template()
    return tree.getroot()

if __name__ == "__main__":
    # Test de chargement
    print("Test de chargement du template embarqué...")
    root = get_minimal_template_root()

    # Vérifier la structure
    midi_tracks = root.findall('.//MidiTrack')
    print(f"✓ Template chargé: {len(midi_tracks)} MidiTrack")

    # Vérifier le Sampler
    samplers = root.findall('.//MultiSampler')
    print(f"✓ {len(samplers)} MultiSampler trouvé(s)")

    print("\\n✓ Template embarqué fonctionnel!")
'''

    # Sauvegarder le fichier Python
    print(f"\n💾 Sauvegarde du code Python...")
    print(f"   {output_path}")

    with open(output_path, 'w') as f:
        f.write(python_code)

    # Statistiques
    original_size = os.path.getsize(template_path)
    python_size = os.path.getsize(output_path)

    print(f"\n📊 Statistiques:")
    print(f"   Template .als: {original_size / 1024:.1f} KB")
    print(f"   Code Python: {python_size / 1024:.1f} KB")
    print(f"   Overhead: {100 * (python_size/original_size - 1):.1f}%")

    print("\n✓ Template embarqué dans le code!")

if __name__ == "__main__":
    import sys

    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, "template_minimal_1track.als")
    output_path = os.path.join(script_dir, "minimal_template.py")

    if not os.path.exists(template_path):
        print(f"❌ Template minimal non trouvé: {template_path}")
        sys.exit(1)

    embed_template(template_path, output_path)
