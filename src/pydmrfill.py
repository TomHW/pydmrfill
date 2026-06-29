#!/usr/bin/python3
'''
Created on 05.05.2026

@author: Thomas Hoffmann <da1th@darc.de>

Gets 2m and 70cm band repeaters from repeaterbook and creates zones and channels for qdmr.
Needs configuration in convert.yaml.
The list of zones should be inside of the given country. Each Zone has the following values:
Name, Latitude, Longitude, MaxDistance (Radius in km). qdmr is limited to ??? channels, you have to limit zones
distances to avoid truncating the channel list during import.

Based on repeaerbook API: <https://www.repeaterbook.com/wiki/doku.php?id=api>
Please note: Program is tested for 'Outside of North America', North America may have different data structures.

Repeaterbook limits the download rate. Make your first query with Mode: 'Dump' to write the raw query result into
a local dump.bin file. Then use Mode: 'Load' to avoid further queries when fine tuning the script and parameters
for your needs. Mode: 'Default' makes repeaterbook queries and makes no dump.bin files, it is for normal use with
proven parameters.   
'''

import requests
import json
import copy
import math
import sys
import csv
import pickle
import yaml
from pathlib import Path
from qdmrupdater import QdmrUpdater
import itertools
import operator
import functools
import time


# globals for get_distance lambda expression
lat = 0.0
lon = 0.0
ch_fm_template = None
ch_dmr_template = None

def to_maiden(lat: float, lon: float, precision: int = 3) -> str:
    """
    Returns a maidenhead string for latitude, longitude at specified level.

    Parameters
    ----------

    lat : float or tuple of float
        latitude or tuple of latitude, longitude
    lon : float, optional
        longitude (if not given tuple)
    precision : int, optional
        level of precision (length of maidenhead grid string output)

    Returns
    -------

    maiden : str
        Maidenhead grid string of specified precision
    """

    # The QTH locator encoding can be treated as a mixed radix integer number.
    # The floating point values will be converted into integers by applying
    # a multiplier that is chosen based on the required level of precision
    # in order to retain accuracy.

    # Do the conversion according to radix starting from right most position
    # returns a generaror  which produce values for each position (from least to most significant)
    # I.e in reverse order.
    def convert(val, radix):
        while radix:
            p, q = divmod(val, radix[-1])
            base = ord("a") if len(radix) == 3 else ord("A")
            yield str(q) if radix[-1] == 10 else chr(q + base)
            val = p
            radix = radix[:-1]

    radix = [18] + [24 if i % 2 else 10 for i in range(precision - 1)]
    multiplier = functools.reduce(operator.mul, radix)

    int_lat = int((lat + 90) * multiplier + .5) // functools.reduce(operator.mul, radix[:2])
    int_lon = int(((lon + 180) % 360) * (multiplier//2) + .5) // functools.reduce(operator.mul, radix[:2])

    maiden = "".join(reversed(list(itertools.chain(*zip(convert(int_lat, radix), convert(int_lon, radix))))))

    return maiden


#Calculate the orthodrom between two positions
def distance(lat1, lon1, lat2, lon2):
    earthRadius = 6371.0  # km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    deltaPhi = math.radians(lat2 - lat1)
    deltaLambda = math.radians(lon2 - lon1)

    a = math.sin(deltaPhi / 2) * math.sin(deltaPhi / 2) + math.cos(phi1) * math.cos(phi2) * math.sin(deltaLambda / 2) * math.sin(deltaLambda / 2);
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));

    d = earthRadius * c  # in km
    return d

#Download repeaters from repeaterbook (json format)
def get_repeaters(url, ua, at):
    headers = {
        'User-Agent': ua,
        'X-RB-App-Token': at
    }
    response = requests.get(url, headers=headers)
    if(response.status_code < 400 ):
        result = []
        repeaters = json.loads(response.content)['results']
#        print(repeaters)
        for rep in repeaters:
            if(rep['Operational Status'] == 'On-air' and (rep['DMR'] == 'Yes' or rep['FM Analog'] == 'Yes')):
#                print(rep)
                result.append(rep)
        return result
    else:
        print(response.status_code)
        return []

def remove_umlaut(s):
    rs = str(s).replace('ü', 'ue').replace('ö', 'oe').replace('ä', 'ae').replace('Ü', 'Ue').replace('Ö', 'Oe').replace('Ä', 'Ae').replace('é', 'e').replace('è', 'e').replace('â', 'a')
    return rs[:16]

#Map repeaterbooLowk entry to GD77 channel format
def map_rep2chn(rep, rowct, ts1_ta, ts2_ta, fm_bw):
    ch_fm = copy.deepcopy(ch_fm_template) 
    ch_dmr = copy.deepcopy(ch_dmr_template)

    maiden = to_maiden(float(rep['Lat']), float(rep['Long']), 4)
    ch = {}
    band = ' '
    if(rep['FM Analog'] == 'Yes'):
        ch_fm['id'] = 'fmch' + str(rowct)
        ch_fm['txFrequency'] = str(float(rep['Input Freq'])) + ' MHz'
        ch_fm['rxFrequency'] = str(float(rep['Frequency'])) + ' MHz'
#        ch_fm['txTone'] = { 'ctcss': rep['PL'] + ' Hz'} if(rep['PL'] != 'CSQ') else None
        ch_fm['txTone'] = { 'ctcss': rep['PL'] + ' Hz'} if(rep['PL'] != '' and rep['PL'] != '1750' and rep['PL'] != 'CSQ') else None
        ch_fm['rxTone'] = { 'ctcss': rep['TSQ'] + ' Hz'} if(rep['TSQ'] != '') else None
        if(float(rep['Input Freq']) > 146):
            band = '#'
        ch_fm['name'] = remove_umlaut(band + rep['Callsign'] + ' '  + rep['Nearest City'])
        ch_fm['bandwidth'] = fm_bw
        if(rep['FM Bandwidth'] == '12.5 kHz'):
            ch_fm['bandwidth'] = 'Small'
        ch_fm['Latitude'] = rep['Lat']
        ch_fm['Longitude'] = rep['Long']
        if('openGD77' in ch_fm):
            ch_fm['openGD77']['location'] = maiden
        ch['fm'] = ch_fm

    if(rep['DMR'] == 'Yes'):
        ch_dmr['id'] = 'dmrch' + str(rowct)
        ch_dmr['txFrequency'] = str(float(rep['Input Freq'])) + ' MHz'
        ch_dmr['rxFrequency'] = str(float(rep['Frequency'])) + ' MHz'
        ch_dmr['colorCode'] = int(rep['DMR Color Code'])
        if(float(rep['Input Freq']) > 146):
            band = '#'
        ch_dmr['name'] = remove_umlaut(band + rep['Callsign'] + '.'  + rep['Nearest City'])
        ch_dmr['Latitude'] = rep['Lat']
        ch_dmr['Longitude'] = rep['Long']
        if('openGD77' in ch_dmr):
            ch_dmr['openGD77']['location'] = maiden
        ch['dmr'] = ch_dmr

    return ch    

#Extract channel name from zone channel dictionary - lambda expression for zone sort
def get_channelNameDistance(chnND):
    return chnND[1]

#Extract channel name from channel dictionary - lambda expression for channel sort
def get_distance(chnDict):
    return distance(float(list(chnDict.values())[0]['Latitude']), float(list(chnDict.values())[0]['Longitude']), lat, lon)

def read_csv_channels(path, fm_bw, idpfx, zonelst):
    channels = []

    with open(path, 'rt', encoding='UTF-8', newline='') as csvinfile:
        chreader = csv.DictReader(csvinfile, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        rowct = 1
        for row in chreader:
            ch_fm = copy.deepcopy(ch_fm_template) 
            ch_dmr = copy.deepcopy(ch_dmr_template)
            maiden = to_maiden(float(row['Latitude'].replace(',', '.')), float(row['Longitude'].replace(',', '.')), 4)
        
            if(row['Channel Type'] == 'Analogue'):
                ch_fm['id'] = 'cfmch' + idpfx + row['Channel Number']
                ch_fm['txFrequency'] = str(float(row['Tx Frequency'].replace(',', '.'))) + ' MHz'
                ch_fm['rxFrequency'] = str(float(row['Rx Frequency'].replace(',', '.'))) + ' MHz'
                ch_fm['txTone'] = { 'ctcss': row['TX Tone'].replace(',', '.') + ' Hz'} if(row['TX Tone'] != 'None') else None
                ch_fm['rxTone'] = { 'ctcss': row['RX Tone'].replace(',', '.') + ' Hz'} if(row['RX Tone'] != 'None') else None
                ch_fm['name'] = remove_umlaut(row['Channel Name'])
                ch_fm['bandwidth'] = fm_bw
                ch_fm['bandwidth'] = 'Small' if(row['Bandwidth (kHz)'] == '12,5') else 'Wide'
                if('openGD77' in ch_fm):
                    ch_fm['openGD77']['location'] = maiden
                channels.append({'fm': ch_fm})
                zonelst.append([ch_fm['id'], 0])
        
            if(row['Channel Type'] == 'Digital'):
                ch_dmr['id'] = 'cdmrch' + idpfx + row['Channel Number']
                ch_dmr['txFrequency'] = str(float(row['Tx Frequency'].replace(',', '.'))) + ' MHz'
                ch_dmr['rxFrequency'] = str(float(row['Rx Frequency'].replace(',', '.'))) + ' MHz'
                ch_dmr['colorCode'] = int(row['Colour Code'])
                ch_dmr['name'] = remove_umlaut(row['Channel Name'])
                if('openGD77' in ch_dmr):
                    ch_dmr['openGD77']['location'] = maiden
                channels.append({'dmr': ch_dmr})
                zonelst.append([ch_dmr['id'], 0])
            rowct += 1

    return channels


def get_repeaterbook_channels(data, itupf):
    myCountry = data['Zones'][itupf]['Country'] # Repeaterbook query for this country
    mode = data['Zones'][itupf]['Mode']
    at = data['API-Token']
    ua = data['User-Agent']
    if (mode == 'Load' and Path(f"dump-{myCountry}.bin").is_file()):
        with open(f"dump-{myCountry}.bin", 'rb') as dumpfile:
            channels2m = pickle.load(dumpfile)
            channels70cm = pickle.load(dumpfile)
    else:
        time.sleep(10)      # Be polite and restrained when making requests.
        url = f'https://www.repeaterbook.com/api/exportROW.php?country={myCountry}&frequency=14%'
        channels2m = get_repeaters(url, ua, at)
        url = f'https://www.repeaterbook.com/api/exportROW.php?country={myCountry}&frequency=43%'
        channels70cm = get_repeaters(url, ua, at)
        if (mode == 'Dump'):
            with open(f"dump-{myCountry}.bin", 'wb') as dumpfile:
                pickle.dump(channels2m, dumpfile)
                pickle.dump(channels70cm, dumpfile) # 2m Band
    return channels2m, channels70cm

def main(argv):
    global ch_fm_template
    global ch_dmr_template
    
    confn = "PyDMRFill.yaml"
    if(len(argv) > 0):
        confn = argv[0]
    with open(confn,"r") as conffile:
        data = yaml.load(conffile,Loader=yaml.SafeLoader)
        
    myQdmr = QdmrUpdater(data['CP-Template'])
       
    have_fm_template = False
    have_dmr_template = False
    ch_fm_template = myQdmr.ch_fm_template
    ch_dmr_template = myQdmr.ch_dmr_template
    for pchn in myQdmr.cp_data['channels']:
        if('fm' in pchn and pchn['fm']['name'][:8] == 'Template'):
            ch_fm_template = copy.deepcopy(pchn['fm'])
            have_fm_template = True
        if('dmr' in pchn and pchn['dmr']['name'][:8] == 'Template'):
            ch_dmr_template = copy.deepcopy(pchn['dmr'])
            have_dmr_template = True
        if(have_fm_template and have_dmr_template):
            break

    myZones = data['Zones']
    channelTypesDict = {}
    channels = []
    chkeepdict = {}
    # save aprs channels
    for posit in myQdmr.cp_data['positioning']:
        if('aprs' in posit):
            chid = posit['aprs']['revert']
            chkeepdict[chid] = 'aprs'
    if('KEEP-ZONES' in data):
        for kzone in data['KEEP-ZONES']:
            for zone in myQdmr.cp_data['zones']:
                if(zone['name'] == kzone):
                    for chid in zone['A']:
                        chkeepdict[chid] = kzone
    for ch in myQdmr.cp_data['channels']:
        if('fm' in ch):
            if(ch['fm']['id'] in chkeepdict):
                channels.append(copy.deepcopy(ch))
        else:
            if(ch['dmr']['id'] in chkeepdict):
                channels.append(copy.deepcopy(ch))
    
    rbCountryChannels  = {}
    rowct = 1
    for itupf in myZones:
        for zoneName in myZones[itupf]['Regions']:
            global lat
            global lon
            region = myZones[itupf]['Regions'][zoneName]
            lat = region['Latitude']
            lon = region['Longitude']
            zchannels = []
            country = myZones[itupf]['Country']
            if(not country in rbCountryChannels):
                rbCountryChannels[country] = get_repeaterbook_channels(data, itupf)
            channels2m, channels70cm = rbCountryChannels[country]
                
            for row in list(channels2m) + list(channels70cm):
                if(len(row['Callsign']) < 4):
                    continue
                dist = distance(float(row['Lat']), float(row['Long']), region['Latitude'], region['Longitude'])
                if(dist > region['MaxDistance']):
                    continue
                print(row['Callsign'] + '.'  + row['Nearest City'] + ': ', f"{dist:5.1f}")
                chn = map_rep2chn(row, rowct, data['TS1-TA'], data['TS2-TA'], data['FM-Bandwidth'])
                # add channel names to zone
                for chtype in chn:
                    if (chtype == 'dmr'):
                        zone = itupf + '-' + zoneName + ' DMR'
                    else:
                        zone = itupf + '-' + zoneName + ' Analog'
                    # channelName isn't unique, need to recognize duplicates! Use dictonary instead of list!
                    if(zone in channelTypesDict):
                        channelTypesDict[zone].append([chn[chtype]['id'], dist])
                    else:
                        channelTypesDict[zone] = list([[chn[chtype]['id'], dist]])
                    rowct += 1
                for elem, li in chn.items():
                    zchannels.append({elem: li}) 
            # sort channels based on ascending distance in current zone
            zchannels.sort(key=get_distance)
            # add sorted channel to global channel list
            channels += zchannels

    if ('CSV-Import' in data):
        czct = 1
        for czone in data['CSV-Import']:
            channelTypesDict[czone] = []
            channels += read_csv_channels(data['CSV-Import'][czone]['Path'], data['FM-Bandwidth'], str(czct), channelTypesDict[czone])
            czct += 1

    outfn = 'out.qdmr.yaml'
    myQdmr.cp_data['channels'] = channels
    zonect = 1
    zones = []
    for zone in myQdmr.cp_data['zones']:
        try:
            if('KEEP-ZONES' in data and data['KEEP-ZONES'].index(zone['name']) >= 0):
                zones.append(zone)
        except ValueError:
            print(zone['name'])
    for elem in channelTypesDict:
        channelTypesDict[elem].sort(key=get_channelNameDistance)
        zchannels = list(channelTypesDict[elem][i][0] for i in range(len(channelTypesDict[elem])))
        zelem = {'id': f"fzone{zonect}", 'name': elem, 'A': zchannels, 'B': [], 'anytone': {'hidden': 'false'}}
        zones.append(zelem)
        zonect += 1
    myQdmr.cp_data['zones'] = zones
    myQdmr.save_as(outfn)
    
    exit(0)
    

if __name__ == '__main__':
    main(sys.argv[1:])
