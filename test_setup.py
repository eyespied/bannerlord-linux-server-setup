import json
from pathlib import Path
import tempfile
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

if __name__=='__main__':unittest.main()
