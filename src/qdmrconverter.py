'''
Created on 30.04.2026

@author: DA1TH - Thomas Hoffmann
'''
import sys
import wrapt
import yaml
from pathlib import Path
from pickle import FALSE
import subprocess


class Loader(yaml.SafeLoader):
    pass

class Dumper(yaml.SafeDumper):
    pass
   
class Qdefault():
    def __init__(self, val):
        self.val = val

class Qselected():
    def __init__(self, val):
        self.val = val



def construct_Qdefault(loader, node):
    return Qdefault(loader.construct_scalar(node))

def construct_Qselected(loader, node):
    return Qselected(loader.construct_scalar(node))

Loader.add_constructor('!default', construct_Qdefault)
Loader.add_constructor('!selected', construct_Qselected)

class Dumper(yaml.SafeDumper):
    pass

def qdefault_representer(dumper: yaml.SafeDumper, ta: Qdefault) -> yaml.nodes.ScalarNode:
    """Represent a tagged instance as a YAML mapping node."""
    return dumper.represent_scalar('!default', ta.val)

def qselected_representer(dumper: yaml.SafeDumper, ta: Qselected) -> yaml.nodes.ScalarNode:
    """Represent a tagged instance as a YAML mapping node."""
    return dumper.represent_scalar('!selected', ta.val)

Dumper.add_representer(Qdefault, qdefault_representer)
Dumper.add_representer(Qselected, qselected_representer)


def remove_umlaut(s):
    rs = str(s).replace('ü', 'ue').replace('ö', 'oe').replace('ä', 'ae').replace('é', 'e').replace('è', 'e').replace('â', 'a')
    return rs[:16]

def convert_channel(ch, dtag):
    fm_at = {'frequencyCorrection': 0, 'handsFree': False, 'aprsPTT': 'Off', 'rxCustomCTCSS': False, 'txCustomCTCSS': False, 'customCTCSS': 0, 'squelchMode': 'Carrier', 'scramblerFrequency': '0 Hz'}
    dmr_at = {'frequencyCorrection': 0, 'handsFree': False, 'aprsPTT': 'Off', 'adaptiveTDMA': False, 'throughMode': False, 'crc': True}
    if('dmr' in ch):
        if(dtag in ch['dmr']):
#            print('DMR: ', ch['dmr'][dtag])
            if(dtag == 'openGD77'):
                ch['dmr']['anytone'] = dmr_at
                ch['dmr']['contact'] = 'cont6'
    elif('fm' in ch):
        if(dtag in ch['fm']):
#            print('FM:  ', ch['fm'][dtag])
            if(dtag == 'openGD77'):
                ch['fm']['anytone'] = fm_at
    else:
        print('--> ', ch)
        
def convert_contact(ct, dtag):
    dmr_at = {'alertType': None}
    if('dmr' in ct):
        if(dtag in ct['dmr']):
#            print('DMR: ', ct['dmr'][dtag])
            if(dtag == 'openGD77'):
                ct['dmr']['anytone'] = dmr_at
                ct['dmr']['name'] = remove_umlaut(ct['dmr']['name'])
#                del ct['dmr'][dtag]
    else:
        print('--> ', ct)

def convert_zone(zo, dtag):
    at = {'hidden': False}
    if(dtag == 'openGD77'):
        zo['anytone'] = at
    else:
        print('--> ', zo)

def convert_positioning(pos, dtag):
    at = {'txDelay': '1200 ms', 'preWaveDelay': '1500 ms', 'passAll': False, 'reportPosition': True, 'reportMicE': True, 'reportObject': True, 'reportItem': True, 'reportMessage': True, 'reportWeather': True, 'reportNMEA': False, 'reportStatus': False, 'reportOther': False, 'frequencies': [{'id': 'af1', 'name': 'APRS 1', 'frequency': '144.64 MHz'}, {'id': 'af2', 'name': 'APRS 2', 'frequency': '144.64 MHz'}, {'id': 'af3', 'name': 'APRS 3', 'frequency': '144.64 MHz'}, {'id': 'af4', 'name': 'APRS 4', 'frequency': '144.64 MHz'}, {'id': 'af5', 'name': 'APRS 5', 'frequency': '144.64 MHz'}, {'id': 'af6', 'name': 'APRS 6', 'frequency': '144.64 MHz'}, {'id': 'af7', 'name': 'APRS 7', 'frequency': '144.64 MHz'}]}
    if('aprs' in pos):
        if(dtag == 'openGD77'):
            pos['anytone'] = at
        else:
            print('--> ', pos['aprs']['anytone'])


def main(argv):
    if(len(argv) < 2):
        sys.exit("Bitte Eingabedatei (OpenGD77 yaml codeplug) und Prefixdatei als Parameter Übergeben!")

    infn = argv[0]
    prefixn = argv[1]
    dtag = 'openGD77'
    if(len(argv) > 2):
        dtag = argv[1] 
    with open(infn, 'r', newline='') as yamlinfile:
        data = yaml.load(yamlinfile, Loader)
    with open(prefixn, 'r', newline='') as yamlprefixinfile:
        prefix_data = yaml.load(yamlprefixinfile, Loader)
    
    for el in data:
        print(el)

    for channel in data['channels']:
        convert_channel(channel, dtag)
    for contact in data['contacts']:
        convert_contact(contact, dtag)
    for zone in data['zones']:
        convert_zone(zone, dtag)
#    for pos in data['positioning']:
#        convert_positioning(pos, dtag)

    out_prefix = {
        'version': [True, False],
        'settings': [True, False],
        'radioIDs': [True, False],
        'contacts': [False, False],
        'groupLists': [False, False],
        'channels': [False, False],
        'zones': [False, False],
        'roamingChannels': [True, False],
        'roamingZones': [True, False],
        'positioning': [False, False],
        'commercial': [False, False],
        'sms': [False, False]
        }
    outfn = 'out.yaml'
    p = Path(outfn)
    p.unlink(missing_ok=True)
    with open(outfn, 'a', newline='') as yamloutfile:
        for tlel, ctrl in out_prefix.items():
            use_prefix = ctrl[0]
            if(use_prefix):
                if(tlel in prefix_data):
                    yaml.dump_all([{tlel: prefix_data[tlel]}], yamloutfile, Dumper=Dumper, default_flow_style=ctrl[1], sort_keys=False)
            else:
                if(tlel in data):
                    yaml.dump_all([{tlel: data[tlel]}], yamloutfile, Dumper=Dumper, default_flow_style=ctrl[1], sort_keys=True)
    
    subprocess.run(["sed", "-i", "-r", "-f", "toqdmr.sed", "out.yaml"])

if __name__ == '__main__':
    main(sys.argv[1:])
