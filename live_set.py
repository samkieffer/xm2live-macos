#!/usr/bin/env python3
"""
Assemblage du set Ableton Live (.als) à partir de fragments enregistrés par Live

Les fragments de templates/ sont des morceaux de set tels que Live les écrit, extraits par
tools/extract_fragments.py d'un set enregistré par Live (à refaire à chaque version de Live) :
  liveset.xml     : le set sans piste MIDI ni groupe (pistes de retour, piste principale, transport)
  midi_track.xml  : une piste MIDI avec un Sampler (une zone de sample) et un clip d'arrangement vide
  group_track.xml : une piste de groupe
  simpler.xml     : un Simpler (instruments qui utilisent l'effet 9xx)

Le set est assemblé en mémoire puis écrit en une fois (XML gzippé), sans fichier temporaire.

Identifiants : seuls ceux qui doivent être uniques dans tout le set sont renumérotés à chaque
copie de fragment (cibles d'automation et de modulation, Pointee, ControllerTargets.N, et l'Id des
pistes). Les index locaux (ClipSlot, KeyTrack, MidiClip, TrackSendHolder...) restent tels que Live
les écrit. NextPointeeId est placé au-delà du plus grand identifiant global.
"""

import os
import copy
import gzip
from lxml import etree

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
FRAGMENTS = ('liveset', 'midi_track', 'group_track', 'simpler')
NO_GROUP = '-1'


def is_global_id(element):
    """Éléments dont l'Id doit être unique dans tout le set (cibles référencées par PointeeId)"""
    return isinstance(element.tag, str) and 'Id' in element.attrib and (
        element.tag.endswith('Target') or element.tag == 'Pointee'
        or element.tag.startswith('ControllerTargets.'))


def load_als(path):
    """Racine XML d'un .als (XML gzippé)"""
    with gzip.open(path, 'rb') as f:
        return etree.fromstring(f.read(), etree.XMLParser(huge_tree=True))


def save_als(root, path):
    """Écrit un .als (XML gzippé)"""
    with gzip.open(path, 'wb', compresslevel=6) as f:
        f.write(etree.tostring(root, xml_declaration=True, encoding='UTF-8'))


def set_value(element, path, value):
    """Attribut Value du sous-élément `path`, s'il existe"""
    target = element.find(path)
    if target is not None:
        target.set('Value', str(value))


# --- Extraction des fragments d'un set enregistré par Live -------------------------------------

def clear(element):
    """Retire tous les enfants d'un élément (s'il existe)"""
    if element is not None:
        for child in list(element):
            element.remove(child)


def clean_sample_ref(sample_part):
    """Zone de sample neutre : pas de chemin ni d'empreinte du sample d'origine"""
    set_value(sample_part, 'Name', '')
    clear(sample_part.find('SampleRef/SourceContext'))  # fichier d'origine retenu par Live
    file_ref = sample_part.find('SampleRef/FileRef')
    if file_ref is not None:
        set_value(file_ref, 'RelativePath', '')
        set_value(file_ref, 'Path', '')
        set_value(file_ref, 'OriginalFileSize', 0)
        set_value(file_ref, 'OriginalCrc', 0)


def clean_device(device):
    """Instrument (Sampler, Simpler) : une seule zone de sample, neutre"""
    parts = device.find('Player/MultiSampleMap/SampleParts')
    if parts is not None:
        for part in list(parts)[1:]:
            parts.remove(part)
        if len(parts):
            clean_sample_ref(parts[0])
    return device


def clean_track(track, keep_device=None):
    """Piste neutre : sans nom, groupe, automation ni note, sortie vers la piste principale

    keep_device: balise du seul instrument à garder (les autres devices sont retirés)
    """
    for field in ('EffectiveName', 'UserName', 'Annotation', 'MemorizedFirstClipName'):
        set_value(track, f'Name/{field}', '')
    set_value(track, 'TrackGroupId', NO_GROUP)
    clear(track.find('AutomationEnvelopes/Envelopes'))
    routing = track.find('DeviceChain/AudioOutputRouting')
    if routing is not None:
        set_value(routing, 'Target', 'AudioOut/Main')
        set_value(routing, 'UpperDisplayString', 'Main')
        set_value(routing, 'LowerDisplayString', '')

    devices = track.find('DeviceChain/DeviceChain/Devices')
    if devices is not None:
        kept = devices.find(keep_device) if keep_device else None
        clear(devices)
        if kept is not None:
            devices.append(clean_device(kept))

    sequencer = track.find('DeviceChain/MainSequencer')
    if sequencer is not None:
        # Clips de session retirés, un seul clip d'arrangement gardé, vide
        for slot_value in sequencer.findall('ClipSlotList/ClipSlot/ClipSlot/Value'):
            clear(slot_value)
        clips = sequencer.find('ClipTimeable/ArrangerAutomation/Events')
        if clips is not None:
            for clip in list(clips)[1:]:
                clips.remove(clip)
            for clip in clips:
                set_value(clip, 'Name', '')
                clear(clip.find('Notes/KeyTracks'))
                clear(clip.find('Envelopes/Envelopes'))
                set_value(clip, 'Notes/NoteIdGenerator/NextId', 1)
        set_value(sequencer, 'Recorder/IsArmed', 'false')
    clear(track.find('TakeLanes/TakeLanes'))
    return track


def extract_fragments(root):
    """Fragments d'un set enregistré par Live : {nom: élément}, pour ceux que le set contient

    liveset : le set sans ses pistes MIDI, audio ni groupes (et sans automation de tempo) ;
    midi_track : la première piste MIDI avec un Sampler ; group_track : la première piste de groupe ;
    simpler : le premier Simpler.
    """
    fragments = {}
    tracks = root.find('LiveSet/Tracks')

    midi_track = next((t for t in tracks.iter('MidiTrack')
                       if t.find('DeviceChain/DeviceChain/Devices/MultiSampler') is not None), None)
    if midi_track is not None:
        fragments['midi_track'] = clean_track(copy.deepcopy(midi_track), keep_device='MultiSampler')
    group_track = tracks.find('GroupTrack')
    if group_track is not None:
        fragments['group_track'] = clean_track(copy.deepcopy(group_track))
    simpler = next(root.iter('OriginalSimpler'), None)
    if simpler is not None:
        fragments['simpler'] = clean_device(copy.deepcopy(simpler))

    liveset = copy.deepcopy(root)
    liveset_tracks = liveset.find('LiveSet/Tracks')
    for track in list(liveset_tracks):
        if track.tag != 'ReturnTrack':
            liveset_tracks.remove(track)
    clear(liveset.find('LiveSet/MainTrack/AutomationEnvelopes/Envelopes'))
    clear(liveset.find('LiveSet/Locators/Locators'))
    fragments['liveset'] = liveset
    return fragments


def load_fragments(template_path=None):
    """Fragments de templates/ ; un set Live personnel (template_path) remplace ceux qu'il contient"""
    parser = etree.XMLParser(huge_tree=True)
    fragments = {name: etree.parse(os.path.join(TEMPLATES_DIR, f'{name}.xml'), parser).getroot()
                 for name in FRAGMENTS}
    if template_path:
        fragments.update(extract_fragments(load_als(template_path)))
    return fragments


# --- Assemblage ------------------------------------------------------------------------------

class LiveSetBuilder:
    """Set en cours d'assemblage : copie de liveset.xml, pistes ajoutées avant les pistes de retour"""

    def __init__(self, template_path=None):
        self.fragments = load_fragments(template_path)
        self.root = copy.deepcopy(self.fragments['liveset'])
        self.live_set = self.root.find('LiveSet')
        self.tracks = self.live_set.find('Tracks')

        global_ids = [int(e.get('Id')) for e in self.root.iter() if is_global_id(e)]
        next_pointee = int(self.live_set.find('NextPointeeId').get('Value'))
        self.next_id = max(global_ids + [next_pointee - 1]) + 1
        self.next_track_id = max([int(t.get('Id')) for t in self.tracks] + [0]) + 1

    @property
    def sample_part(self):
        """Zone de sample du Sampler de midi_track.xml (modèle de chaque zone)"""
        return self.fragments['midi_track'].find(
            'DeviceChain/DeviceChain/Devices/MultiSampler/Player/MultiSampleMap/SampleParts/MultiSamplePart')

    def new_id(self):
        """Identifiant global libre (cible d'automation créée par le convertisseur)"""
        self.next_id += 1
        return self.next_id - 1

    def renumber(self, element):
        """Nouveaux identifiants globaux pour une copie de fragment (et ses PointeeId internes)"""
        mapping = {}
        for target in element.iter():
            if is_global_id(target):
                mapping[target.get('Id')] = str(self.new_id())
                target.set('Id', mapping[target.get('Id')])
        for pointee in element.iter('PointeeId'):
            if pointee.get('Value') in mapping:
                pointee.set('Value', mapping[pointee.get('Value')])
        return element

    def copy_fragment(self, name):
        """Copie d'un fragment, identifiants renumérotés"""
        return self.renumber(copy.deepcopy(self.fragments[name]))

    def add_track(self, name, before=None):
        """Ajoute une piste ('midi_track' ou 'group_track') avant `before`, sinon avant les retours"""
        track = self.copy_fragment(name)
        track.set('Id', str(self.next_track_id))
        self.next_track_id += 1
        self.fit_slots(track)
        if before is None:
            before = self.tracks.find('ReturnTrack')
        if before is None:
            self.tracks.append(track)
        else:
            before.addprevious(track)
        return track

    def fit_slots(self, track):
        """Un emplacement de clip par scène du set (les fragments peuvent venir de sets différents)"""
        scenes = len(self.live_set.find('Scenes'))
        for slots in (track.find('Slots'), track.find('DeviceChain/MainSequencer/ClipSlotList')):
            if slots is None or not len(slots):
                continue
            while len(slots) > scenes:
                slots.remove(slots[-1])
            while len(slots) < scenes:
                slot = self.renumber(copy.deepcopy(slots[-1]))
                slot.set('Id', str(len(slots)))
                slots.append(slot)

    def save(self, path):
        self.live_set.find('NextPointeeId').set('Value', str(self.next_id))
        save_als(self.root, path)
