#!/usr/bin/env python3
"""SSH/SCP helper usable from Windows, macOS or Linux with Python 3 and OpenSSH."""
import argparse
import re
import shlex
import subprocess
import uuid
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--host',required=True,help='SSH config alias or user@host')
p.add_argument('--repo',default='/opt/bannerlord-linux-server-setup')
p.add_argument('action',choices=['status','start','stop','restart','logs','backup','token','menu','update','apply-update','render','config','upload-mods'])
p.add_argument('name',nargs='?');p.add_argument('file',nargs='?');a=p.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_@.:-]+',a.host) or a.host.startswith('-'):p.error('Invalid SSH host')
if not re.fullmatch(r'/[A-Za-z0-9_./-]+',a.repo) or '..' in Path(a.repo).parts:p.error('Invalid remote repository path')
if a.name and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}',a.name):p.error('Invalid instance name')
uploaded=None
upload_dir=None
try:
    arguments=['sudo','python3',a.repo+'/bl.py','--settings',a.repo+'/settings.json',a.action]
    if a.name:arguments.append(a.name)
    if a.action in ('config','upload-mods'):
        if not a.file or not Path(a.file).is_file():p.error('Provide a local file')
        upload_dir='/tmp/bannerlord-upload-'+uuid.uuid4().hex
        subprocess.run(['ssh',a.host,shlex.join(['mkdir','-m','700','--',upload_dir])],check=True)
        uploaded=upload_dir+'/payload'
        subprocess.run(['scp','--',a.file,a.host+':'+uploaded],check=True)
        arguments.append(uploaded)
    subprocess.run(['ssh','-t',a.host,shlex.join(arguments)],check=True)
finally:
    if uploaded:subprocess.run(['ssh',a.host,'rm -f -- '+shlex.quote(uploaded)],check=False)
    if uploaded:subprocess.run(['ssh',a.host,'rmdir -- '+shlex.quote(upload_dir)],check=False)
