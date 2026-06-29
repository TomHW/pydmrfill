'''
Created on 08.06.2026

@author: sesth
'''
import json
import copy
import math
import sys
import csv
import pickle
import yaml
from pathlib import Path
import subprocess
import tempfile
from test.support.os_helper import unlink


# overwrite Loader and Dumper to match qdmr special types
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

class Qbandwidth():
    def __init__(self, val):
        self.val = val

class Qswitch():
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




class QdmrUpdater(object):
    '''
    Reads and writes yaml files for qdmr
    '''
    cp_file = None
    cp_data = None
    sections = [
        'version',
        'settings',
        'radioIDs',
        'contacts',
        'groupLists',
        'channels',
        'zones',
        'roamingChannels',
        'roamingZones',
        'positioning',
        'commercial',
        'sms'
    ]
    ch_fm_template = {'id': 'tch1',
    'name': '<empty>',
    'rxFrequency': '430.0 MHz',
    'txFrequency': '430.0 MHz',
    'timeout': Qdefault(''),
    'rxOnly': False,
    'vox': Qdefault(''),
    'squelch': Qdefault(''),
    'admit': 'Always',
    'rxTone': {'ctcss': '123.0 Hz'},
    'txTone': {'ctcss': '123.0 Hz'},
    'bandwidth': 'Small',
    'extended': {'talkaround': False,
                'reverseBurst': False},
    'anytone': {'frequencyCorrection': 0,
        'handsFree': False,
        'aprsPTT': False,
        'rxCustomCTCSS': False,
        'txCustomCTCSS': False,
        'customCTCSS': 0,
        'squelchMode': 'SubTone',
        'scramblerFrequency': '0 Hz'},
    'power': 'High'}

    ch_dmr_template = {'id': 'tch2',
        'name': '<empty>',
        'rxFrequency': '430.0000 MHz',
        'txFrequency': '430.0000 MHz',
        'timeout': Qdefault(''),
        'rxOnly': False,
        'vox': Qdefault(''),
        'admit': 'Always',
        'colorCode': 1,
        'timeSlot': 'TS1',
        'radioId': Qdefault(''),
        'groupList': 'grp4',
        'contact': 'cont6',
        'roaming': Qdefault(''),
        'extended': {'talkaround': False,
            'privateCallConfirm': False,
            'sms': True,
            'smsConfirm': False,
            'dataConfirm': True,
            'dcdm': False,
            'loneWorker': False},
        'anytone': {'frequencyCorrection': 0,
            'handsFree': False,
            'aprsPTT': False,
            'adaptiveTDMA': False,
            'throughMode': False,
            'crc': True},
        'power': 'High'}

    def __init__(self, filepath):
        '''
        Constructor
        '''
        if(Path(filepath).is_file()):
            self.cp_file = filepath
            self.open()
        else:
            raise FileNotFoundError()
        
    def open(self):
        '''
        Reads given yaml Codeplug into python.
        '''
        with open(self.cp_file,"r") as qdmrfile:
            self.cp_data = yaml.load(qdmrfile,Loader)

    def save_as(self, filepath):
        '''
        Writes python data to yaml Codeplug.
        '''
        with open(filepath, 'wt', newline='') as yamloutfile:
            for section in self.sections:           # force qdmr order!
                if(section in self.cp_data):
                    yaml.dump({section: self.cp_data[section]}, yamloutfile, Dumper, default_flow_style=False)
                    
        # Ugly formatting hack ;-)            
        sedfn = 'py2qdmr.sed'
        with open(sedfn, 'wt', newline='') as sedoutfile:
            sedoutfile.write('''
s/(vox|keyTone|fmMicGain): false/\\1: off/g
s/bandwidth: Small/bandwidth: Narrow/g
s/(steType|funcK[^:]+|direction[^:]+|monitorSlotMatch|talkerAliasSource|aprsPTT): false/\\1: Off/g
            ''')
        subprocess.run(["sed", "-i", "-r", "-f", sedfn, filepath])
        unlink(sedfn)
        
    def save(self):
        '''
        Writes python data back to original Codeplug
        '''
        self.save_as(self.cp_file)
        
