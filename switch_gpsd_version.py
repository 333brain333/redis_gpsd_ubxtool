#!/usr/bin/env python3
'''
Switches a version of the gpsd,
cgps, ubxtool and gps librairy to the given.
All files should be existant.
'''
from posixpath import curdir
from subprocess import Popen, PIPE
import argparse
import os
import re


parser = argparse.ArgumentParser(description=__doc__)
#parser.add_argument('old_version', type = str, default='',
#help='Version to check from')
#parser.add_argument('new_version', type = str, default='',
#help='Version to check in')
#args = parser.parse_args()


def prepare_version_list()->str:
    print(f'There are next verions avaliable:')
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    files = [i for i in os.listdir(os.path.join(cur_dir, 'gpsd_versions','arm'))\
         if os.path.isfile(os.path.join(cur_dir, 'gpsd_versions','arm',i))]
    s = []
    for file in files:
        s.append(file.split('_')[1])
    s=set(s)
    numeration = list(range(len(s)))
    dic = dict(zip(numeration, s))
    print(dic)
    version = int(input("Type number of a version (1,2,etc)"))
    return dic[version]

def run(cmd:str,std_out:bool=True,std_err:bool=False)->str:
    print(cmd)
    proc = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    out, err= proc.communicate()
    print(err)
    if std_out == True and std_err == True:
        return(out, err)
    if std_err == True:
        return err.decode('utf-8')
    else:
        return out.decode('utf-8')

def rename_blob(ver:str)->None:
    rm_symb_link = [
    f'sudo mv /usr/local/sbin/gpsd /usr/local/sbin/gpsd_{ver}',
    f'sudo mv /usr/local/bin/cgps /usr/local/bin/cgps_{ver}',
    f'sudo mv /usr/local/bin/ubxtool /usr/local/bin/ubxtool_{ver}',
    f'sudo mv /usr/local/lib/python3/dist-packages/gps /usr/local/lib/python3/dist-packages/gps_{ver}',
    f'sudo mv /usr/lib/python3/dist-packages/gps /usr/local/lib/python3/dist-packages/gps_{ver}'
    ]
    for cmd in rm_symb_link:
        run(cmd)

def copy_version(ver: str)->None:
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    run(f'sudo rsync -r {cur_dir}/gpsd_versions/arm/gpsd_{ver} /usr/local/sbin/gpsd_{ver}')
    run(f'sudo rsync -r {cur_dir}/gpsd_versions/arm/cgps_{ver} /usr/local/bin/cgps_{ver}')
    run(f'sudo rsync -r {cur_dir}/gpsd_versions/arm/ubxtool_{ver} /usr/local/bin/ubxtool_{ver}')
    run(f'sudo rsync -r {cur_dir}/gpsd_versions/arm/gps_{ver} /usr/local/lib/python3/dist-packages/gps_{ver}')
    run(f'sudo rsync -r {cur_dir}/gpsd_versions/arm/gps_{ver} /usr/lib/python3/dist-packages/gps_{ver}')

def remove_symb_link()->None:
    run('sudo rm /usr/local/sbin/gpsd')
    run('sudo rm /usr/local/bin/cgps')
    run('sudo rm /usr/local/bin/ubxtool')
    run('sudo rm /usr/local/lib/python3/dist-packages/gps')
    run('sudo rm /usr/lib/python3/dist-packages/gps')

def create_links(ver:str)->None:
    run(f'sudo ln -s /usr/local/sbin/gpsd_{ver} /usr/local/sbin/gpsd')
    run(f'sudo ln -s /usr/local/bin/cgps_{ver} /usr/local/bin/cgps')
    run(f'sudo ln -s /usr/local/bin/ubxtool_{ver} /usr/local/bin/ubxtool')
    run(f'sudo ln -s /usr/local/lib/python3/dist-packages/gps_{ver} /usr/local/lib/python3/dist-packages/gps')
    run(f'sudo ln -s /usr/lib/python3/dist-packages/gps_{ver} /usr/lib/python3/dist-packages/gps')

if __name__=='__main__':
    new_version = prepare_version_list()
    old_version = run('gpsd -V')
    try:
        old_version = re.search('3.[0-9]*', old_version).group()
    except AttributeError:
        old_version=None
    print(f"New version: {new_version}, old version: {old_version}")
    if old_version == None:
        copy_version(new_version)
    elif run(f'find /usr/local/sbin/gpsd -maxdepth 1 -type l -ls')=='':
        rename_blob(old_version)
        copy_version(new_version)
    else:
        remove_symb_link()
    create_links(new_version)