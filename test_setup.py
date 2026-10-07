import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch, MagicMock
import zipfile
import bl

class SetupTests(unittest.TestCase):
    def test_example_valid(self):
        self.assertEqual(2,len(bl.load('settings.example.json')['instances']))

    def test_bad_root_port_and_modules_rejected(self):
        original=json.loads(Path('settings.example.json').read_text())
        for field,value in [('root','/'),('port',7210),('modules',['Native','Bad*Module'])]:
            data=json.loads(json.dumps(original))
            if field=='root':data[field]=value
            else:data['instances'][1][field]=value
            with tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/'s.json';f.write_text(json.dumps(data))
                with self.assertRaises(ValueError):bl.load(f)

    def test_archive_traversal_backslash_collision_link_rejected(self):
        for names in [['../escape'],['/absolute'],['mod/a','mod/A'],['link']]:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);z=p/'input.zip'
                with zipfile.ZipFile(z,'w') as f:
                    for name in names:
                        info=zipfile.ZipInfo(name)
                        if name=='link':info.external_attr=0o120777 << 16
                        f.writestr(info,'test')
                with self.assertRaises(ValueError):bl.safe_extract(z,p/'unpacked')
                self.assertFalse((p/'escape').exists())

    def test_archive_backslash_rejected_on_linux_reader(self):
        # Windows ZipInfo normalises backslashes on read; emulate the Linux
        # reader's unmodified filename to exercise the host-side guard.
        info=zipfile.ZipInfo('escape');info.filename='X'+chr(92)+'escape'
        archive=MagicMock();archive.__enter__.return_value=archive
        archive.infolist.return_value=[info]
        with patch('bl.zipfile.ZipFile',return_value=archive):
            with self.assertRaises(ValueError):bl.safe_extract('ignored','ignored')
        archive.extractall.assert_not_called()

    def test_archive_extracts_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);z=p/'module.zip'
            with zipfile.ZipFile(z,'w') as f:f.writestr('Example/SubModule.xml','<Module/>')
            bl.safe_extract(z,p/'unpacked')
            self.assertTrue((p/'unpacked/Example/SubModule.xml').is_file())

    def test_compose_isolated_and_token_not_in_environment(self):
        s=bl.load('settings.example.json')
        with tempfile.TemporaryDirectory() as tmp,patch('bl.layout',return_value=Path(tmp)):
            bl.write_compose(s)
            services=json.loads((Path(tmp)/'compose.json').read_text())['services']
            self.assertNotEqual(services['server1']['volumes'],services['server2']['volumes'])
            self.assertNotIn('TW_TOKEN',services['server1']['environment'])
            self.assertIn('7210:7210/udp',services['server1']['ports'])

    @unittest.skipUnless(sys.platform.startswith('linux'),'Host copy/backup integration requires Linux')
    def test_upload_config_and_update_preserve_other_instance(self):
        s=bl.load('settings.example.json')
        original_run=subprocess.run
        def commands(args,**kwargs):
            if args[:2]==['docker','inspect']:
                return subprocess.CompletedProcess(args,1,stdout='',stderr='')
            return original_run(args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp,patch('bl.layout',return_value=Path(tmp)),patch('bl.subprocess.run',side_effect=commands):
            root=Path(tmp)
            for name in ('server1','server2'):
                home=root/'instances'/name
                (home/'game/Modules/Native').mkdir(parents=True)
                (home/'game/Modules/Native/server-config.txt').write_text('original '+name)
                (home/'token').write_text('private fixture')
            home=root/'instances/server1'
            z=root/'module.zip'
            with zipfile.ZipFile(z,'w') as archive:
                archive.writestr('Example/SubModule.xml','<Module><Id value="Example"/></Module>')
                archive.writestr('Example/content.txt','custom content')
            bl.upload(s,'server1',z)
            self.assertEqual('custom content',(home/'game/Modules/Example/content.txt').read_text())
            with zipfile.ZipFile(z,'w') as archive:archive.writestr('Native/SubModule.xml','<Module/>')
            with self.assertRaises(ValueError):bl.upload(s,'server1',z)
            base=root/'base/Modules/Native';base.mkdir(parents=True)
            (base/'updated.txt').write_text('new base')
            bl.apply_update(s,'server1')
            self.assertEqual('new base',(home/'game/Modules/Native/updated.txt').read_text())
            self.assertEqual('original server1',(home/'game/Modules/Native/server-config.txt').read_text())
            self.assertEqual('custom content',(home/'game/Modules/Example/content.txt').read_text())
            self.assertEqual('private fixture',(home/'token').read_text())
            self.assertEqual('original server2',(root/'instances/server2/game/Modules/Native/server-config.txt').read_text())
            self.assertEqual(2,len(list((root/'backups').glob('*.tar.gz'))))

if __name__=='__main__':unittest.main()
