"""Read-only tests; no real block devices, formatting or flash calls."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from flash import select_part

def disk(prefix='/dev/nvme0n1'):
    return {'path':prefix,'type':'disk','children':[
      {'path':prefix+'p9','type':'part','partlabel':'Super','partuuid':'uuid-super'},
      {'path':prefix+'p11','type':'part','partlabel':'userdata','partuuid':'uuid-data'},
      {'path':prefix+'p6','type':'part','partlabel':'metadata','partuuid':'uuid-meta'}]}

class Selection(unittest.TestCase):
    def test_case_and_device_names(self):
        for prefix in ('/dev/nvme1n1','/dev/mmcblk0'):
            self.assertEqual(select_part(disk(prefix),'super')['path'],prefix+'p9')
    def test_uuid_handles_nonstandard_gpt_name(self):
        d=disk();d['children'][0]['partlabel']='Android container'
        self.assertEqual(select_part(d,'super','PARTUUID=UUID-SUPER')['path'],'/dev/nvme0n1p9')
    def test_rejects_another_disk(self):
        with self.assertRaises(ValueError):select_part(disk(),'super','/dev/nvme1n1p9')
    def test_rejects_missing_and_duplicate_label(self):
        d=disk();d['children'][0]['partlabel']='other'
        with self.assertRaises(ValueError):select_part(d,'super')
        d=disk();d['children'].append(dict(d['children'][0],path='/dev/nvme0n1p12'))
        with self.assertRaises(ValueError):select_part(d,'super')
    def test_does_not_treat_filesystem_data_label_as_userdata(self):
        d=disk();d['children'][1].update(partlabel='Data',label='userdata',fstype='ntfs')
        with self.assertRaises(ValueError):select_part(d,'userdata')

if __name__=='__main__':unittest.main()
