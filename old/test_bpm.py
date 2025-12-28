#!/usr/bin/env python3
import gzip
import xml.etree.ElementTree as ET

files = {
    'script': '/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor.als',
    'manual': '/Users/sam/Music/Compo/All Compo/Modules/censor_Ableton_Project/censor avec BPM Project/censor avec BPM.als'
}

for name, path in files.items():
    print(f"\n=== {name.upper()} ===")
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
            root = tree.getroot()

            tempo_count = 0
            for elem in root.iter():
                if elem.tag == 'Tempo':
                    manual_elem = elem.find('Manual')
                    if manual_elem is not None:
                        tempo_count += 1
                        val = manual_elem.get('Value')
                        print(f"  Tempo {tempo_count}: {val}")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
