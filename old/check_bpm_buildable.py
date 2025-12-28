#!/usr/bin/env python3
from buildable.live_set import LiveSet

files = [
    ('/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor copie Project/censor copie.als', 'BON (193)'),
    ('/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor.als', 'SCRIPT (120)')
]

for file_path, label in files:
    print(f"\n=== {label} ===")
    try:
        ls = LiveSet.from_file(file_path)

        # Chercher les 3 premiers Tempo
        count = 0
        for elem in ls.element.iter('Tempo'):
            manual = elem.find('Manual')
            if manual is not None:
                count += 1
                print(f"  Tempo {count}: {manual.get('Value')}")
                if count >= 3:
                    break

        if count == 0:
            print("  Aucun Tempo trouvé")

    except Exception as e:
        print(f"  Erreur: {e}")
        import traceback
        traceback.print_exc()
