#!/usr/bin/env python3
"""Generic, root-operated host tooling. Never invokes a shell for user input."""
import argparse
import datetime
import getpass
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,47}\Z")
IMAGE = "bannerlord-runtime:6.0.36"
STAMP = lambda: datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

def run(*args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)

def load(file):
    s = json.loads(Path(file).read_text(encoding='utf-8-sig'))
    # Provisioning is deliberately confined to a new /srv directory.
    if not re.fullmatch(r'/srv/[A-Za-z][A-Za-z0-9_-]{0,47}', s['root']):
        raise ValueError('root must be a direct named directory under /srv')
    names, ports = set(), set()
    if not s.get('instances'): raise ValueError('Add at least one instance')
    for i in s['instances']:
        if not NAME.fullmatch(i['name']) or i['name'] in names: raise ValueError('Invalid/duplicate instance name')
        if type(i['port']) is not int or not 1024 <= i['port'] <= 65535 or i['port'] in ports: raise ValueError('Invalid/duplicate port')
        if type(i['tickrate']) is not int or not 10 <= i['tickrate'] <= 120: raise ValueError('Tickrate must be 10–120')
        if i.get('restart', 'unless-stopped') not in ('no','unless-stopped','on-failure'): raise ValueError('Invalid restart policy')
        if not i['modules'] or len(set(i['modules'])) != len(i['modules']) or any(not NAME.fullmatch(m) for m in i['modules']): raise ValueError('Invalid module order')
        if i['modules'][:2] != ['Native','Multiplayer']: raise ValueError('Modules must begin with Native, Multiplayer')
        names.add(i['name']); ports.add(i['port'])
    return s

def layout(s):
    root = Path(s['root'])
    if root.is_symlink(): raise ValueError('Root may not be a symlink')
    marker = root/'.bannerlord-setup-owned'
    if root.exists() and not marker.is_file(): raise ValueError('Refusing an existing unmanaged root')
    return root

def instance(s, name):
    i = next((i for i in s['instances'] if i['name'] == name), None)
    if not i: raise ValueError('Unknown instance')
    return i, layout(s)/'instances'/name

def compose(s, *args):
    return run('docker','compose','-p',Path(s['root']).name,'-f',layout(s)/'compose.json',*args)

def write_compose(s):
    root=layout(s); services={}
    for i in s['instances']:
        home=root/'instances'/i['name']
        services[i['name']]={
            'image':IMAGE,'container_name':root.name+'-'+i['name'],
            'volumes':[str(home/'game')+':/game',str(home/'token')+':/run/secrets/token:ro'],
            'environment':{'MODULES':'_MODULES_*'+'*'.join(i['modules'])+'*_MODULES_', 'PORT':str(i['port']), 'TICKRATE':str(i['tickrate'])},
            'ports':[f"{i['port']}:{i['port']}/udp",f"{i['port']}:{i['port']}/tcp"],
            'restart':i.get('restart','unless-stopped'),'stdin_open':True,'tty':True,
            'logging':{'driver':'json-file','options':{'max-size':'20m','max-file':'3'}}}
    (root/'compose.json').write_text(json.dumps({'services':services},indent=2)+'\n')

def steam(s):
    root=layout(s); target=root/'base'; steamdir=root/'steamcmd'
    steamdir.mkdir(parents=True,exist_ok=True); target.mkdir(exist_ok=True)
    run('chown','-R','bl-download:bl-download',steamdir,target)
    if not (steamdir/'steamcmd.sh').exists():
        with tempfile.NamedTemporaryFile() as f:
            urllib.request.urlretrieve('https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz',f.name)
            os.chmod(f.name,0o644)
            run('runuser','-u','bl-download','--','tar','-xzf',f.name,'-C',steamdir)
    run('runuser','-u','bl-download','--','env','HOME=/var/lib/bl-download',steamdir/'steamcmd.sh',
        '+force_install_dir',target,'+@sSteamCmdForcePlatformType','linux','+login','anonymous','+app_update','1863440','validate','+quit')
    if not (target/'bin/Linux64_Shipping_Server/TaleWorlds.Starter.DotNetCore.Linux.dll').is_file():
        raise ValueError('Steam installation is missing the Linux launcher')
    # Match the ASP.NET runtime assembly overlay required by the two proven deployments.
    run('docker','run','--rm','-v',str(target)+':/game', '--entrypoint','sh',IMAGE,'-c',
        'for f in /usr/share/dotnet/shared/Microsoft.AspNetCore.App/6.0.36/*; do cp -n "$f" /game/bin/Linux64_Shipping_Server/; done')

def provision(s):
    root=layout(s); root.mkdir(parents=True,exist_ok=True); (root/'.bannerlord-setup-owned').touch()
    run('docker','build','-t',IMAGE,HERE/'runtime')
    steam(s)
    for i in s['instances']:
        _,home=instance(s,i['name']);home.mkdir(parents=True,exist_ok=True)
        if not (home/'game').exists():
            run('cp','-a','--reflink=auto',root/'base',home/'game')
            config=home/'game/Modules/Native/server-config.txt'
            shutil.copy2(HERE/'config.example.txt',config)
            config.chmod(0o600)
        token=home/'token'
        if not token.exists():token.touch(mode=0o600)
    write_compose(s)

def stopped(s,name):
    i,home=instance(s,name)
    q=subprocess.run(['docker','inspect','--format','{{.State.Running}}',Path(s['root']).name+'-'+name],capture_output=True,text=True)
    if q.returncode == 0 and q.stdout.strip() == 'true': raise ValueError('Stop this instance before editing or uploading')
    return i,home

def ready(s,name):
    i,home=instance(s,name)
    if not (home/'token').read_text().strip():raise ValueError('Set the private token first')
    cfg=(home/'game/Modules/Native/server-config.txt').read_text()
    if 'REPLACE_ME' in cfg:raise ValueError('Replace placeholder admin password in config')
    if not re.search(r'^AdminPassword\s+\S+',cfg,re.M):raise ValueError('Set an admin password for the built-in web panel')
    for m in i['modules']:
        if not (home/'game/Modules'/m/'SubModule.xml').is_file():raise ValueError('Missing module: '+m)

def safe_extract(archive,dest):
    """Bounded ZIP input; no links, traversal, duplicate paths or case collisions."""
    with zipfile.ZipFile(archive) as z:
        seen=set(); total=0
        if len(z.infolist()) > 100000:raise ValueError('Too many archive files')
        for f in z.infolist():
            p=PurePosixPath(f.filename)
            if chr(92) in f.filename or ':' in f.filename or p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe ZIP path')
            key=str(p).rstrip('/').casefold()
            if key in seen:raise ValueError('Duplicate ZIP path')
            seen.add(key)
            if stat.S_ISLNK(f.external_attr >> 16):raise ValueError('ZIP symlinks forbidden')
            total+=f.file_size
            if total > 20*1024**3:raise ValueError('Unpacked archive exceeds 20 GiB')
        z.extractall(dest)

def backup(s,name):
    _,home=stopped(s,name); folder=layout(s)/'backups';folder.mkdir(exist_ok=True,mode=0o700)
    target=folder/(name+'-'+STAMP()+'.tar.gz')
    run('tar','-czf',target,'-C',home,'game','token');target.chmod(0o600)
    print('Private backup:',target)

def upload(s,name,archive):
    _,home=stopped(s,name)
    with tempfile.TemporaryDirectory(dir=home) as tmp:
        stage=Path(tmp);safe_extract(archive,stage)
        dirs=list(stage.iterdir())
        if not dirs or any(not d.is_dir() or not NAME.fullmatch(d.name) or d.name in ('Native','Multiplayer') or not (d/'SubModule.xml').is_file() for d in dirs):
            raise ValueError('ZIP must contain module folders with SubModule.xml; native modules cannot be replaced')
        import xml.etree.ElementTree as ET
        for d in dirs:
            mid=ET.parse(d/'SubModule.xml').getroot().find('Id')
            if mid is None or mid.attrib.get('value') != d.name:raise ValueError('Folder must match manifest Id')
        backup(s,name)
        modules=home/'game/Modules'; previous=home/('previous-modules-'+STAMP());previous.mkdir()
        moved=[]; installed=[]
        try:
            for d in dirs:
                dest=modules/d.name
                if dest.exists():dest.rename(previous/d.name);moved.append(d.name)
                d.rename(dest);installed.append(d.name)
        except BaseException:
            for n in installed:shutil.rmtree(modules/n)
            for n in moved:(previous/n).rename(modules/n)
            raise
    print('Modules uploaded; set module order in settings.json, run render, then start. No automatic restart.')

def apply_update(s,name):
    _,home=stopped(s,name);base=layout(s)/'base'
    backup(s,name)
    stage=home/('new-game-'+STAMP())
    run('cp','-a','--reflink=auto',base,stage)
    old=home/'game'
    for module in (old/'Modules').iterdir():
        if module.is_dir() and module.name not in ('Native','Multiplayer'):
            shutil.copytree(module,stage/'Modules'/module.name,dirs_exist_ok=True)
    scenes=old/'Modules/Multiplayer/SceneObj'
    if scenes.exists():
        for scene in scenes.iterdir():
            dest=stage/'Modules/Multiplayer/SceneObj'/scene.name
            if scene.is_dir() and not dest.exists():shutil.copytree(scene,dest)
    shutil.copy2(old/'Modules/Native/server-config.txt',stage/'Modules/Native/server-config.txt')
    previous=home/('previous-game-'+STAMP())
    old.rename(previous)
    try:stage.rename(old)
    except BaseException:previous.rename(old);raise
    print('Updated this stopped instance. Previous game:',previous)
    print('Token, server config, custom modules and custom Multiplayer scenes preserved. Start and verify logs/gameplay; mod compatibility requires checking after game updates.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',default='settings.json')
    p.add_argument('action',choices=['validate','plan','provision','render','status','start','stop','restart','logs','token','config','upload-mods','update','apply-update','backup','menu'])
    p.add_argument('name',nargs='?');p.add_argument('file',nargs='?');a=p.parse_args();s=load(a.settings)
    if a.action in ('validate','plan'):
        print('Settings valid. Isolated instance folders and TCP/UDP ports:')
        for i in s['instances']:print(i['name'],i['port'],','.join(i['modules']))
        return
    if not hasattr(os,'geteuid') or os.geteuid()!=0:raise ValueError('Host operations require sudo on Linux')
    operation_lock=None
    if a.action not in ('status','logs','menu'):
        import fcntl
        root=layout(s)
        if a.action=='provision':
            root.mkdir(parents=True,exist_ok=True);(root/'.bannerlord-setup-owned').touch()
        if not (root/'.bannerlord-setup-owned').exists():raise ValueError('Run bootstrap first')
        operation_lock=(root/'.operation-lock').open('a')
        try:fcntl.flock(operation_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another setup/update operation is running; try again after it finishes')
    if a.action=='provision':provision(s);return
    root=layout(s)
    if not (root/'.bannerlord-setup-owned').exists():raise ValueError('Run bootstrap first')
    if a.action=='render':write_compose(s);return
    if a.action=='status':compose(s,'ps');return
    if a.action=='update':
        # Update only the template. Existing instances stay unchanged until manually selected.
        steam(s);print('Base updated. Use apply-update for each backed-up stopped instance; existing games unchanged.');return
    if a.action=='menu':
        while True:
            print('\n1 Status  2 Start  3 Stop  4 Restart  5 Logs  6 Backup  Q Quit')
            choice=input('Action: ').strip().lower()
            if choice=='q':return
            action={'1':'status','2':'start','3':'stop','4':'restart','5':'logs','6':'backup'}.get(choice)
            if not action:continue
            name=None if action=='status' else input('Instance: ').strip()
            try:run('python3',HERE/'bl.py','--settings',Path(a.settings).resolve(),action,*([name] if name else []))
            except subprocess.CalledProcessError:print('Action failed; see diagnostic above.')
    if not a.name:raise ValueError('Specify an instance name')
    i,home=instance(s,a.name)
    if a.action in ('start','restart'):
        ready(s,a.name);write_compose(s);compose(s,'up','-d',*(['--force-recreate'] if a.action=='restart' else []),a.name)
    elif a.action=='stop':compose(s,'stop',a.name)
    elif a.action=='logs':compose(s,'logs','--tail','100','-f',a.name)
    elif a.action=='backup':backup(s,a.name)
    elif a.action=='apply-update':apply_update(s,a.name)
    elif a.action=='token':
        stopped(s,a.name);value=getpass.getpass('Private TaleWorlds token (not echoed): ').strip()
        if not value or any(c.isspace() for c in value):raise ValueError('Invalid token')
        token=home/'token';token.write_text(value+'\n');token.chmod(0o600)
    elif a.action=='config':
        stopped(s,a.name)
        if not a.file:raise ValueError('Specify a config file')
        cfg=Path(a.file).read_text(encoding='utf-8-sig')
        backup(s,a.name);target=home/'game/Modules/Native/server-config.txt';target.write_text(cfg);target.chmod(0o600)
    elif a.action=='upload-mods':
        if not a.file:raise ValueError('Specify a ZIP')
        upload(s,a.name,a.file)

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError,zipfile.BadZipFile) as e:
        raise SystemExit('ERROR: '+str(e))
