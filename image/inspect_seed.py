"""Read three known package files from private seeds without exporting or modifying them."""
import argparse
from pathlib import Path
import tempfile
from build_image import mounted,run

parser=argparse.ArgumentParser()
parser.add_argument('--base',required=True,type=Path)
parser.add_argument('--state',required=True,type=Path)
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='pf-seed-readonly-') as folder:
 work=Path(folder)
 with mounted(args.base,work/'base',True) as base:
  with mounted(args.state,work/'state',True) as state:
   merged=work/'merged';merged.mkdir()
   run('mount','-t','overlay','-o',f'ro,xino=on,lowerdir={state}/upper:{base}','overlay',merged)
   try:
    for relative in ['usr/bin/glmark2','usr/bin/glmark2-es2','usr/include/turbojpeg.h']:
     for name,root in [('merged',merged),('base',base),('upper',state/'upper')]:
      path=root/relative
      if path.is_file():
       st=path.stat()
       with path.open('rb') as stream: magic=stream.read(4).hex()
       print(f'{name} {relative} dev={st.st_dev} inode={st.st_ino} links={st.st_nlink} bytes={st.st_size} magic={magic}')
   finally:run('umount',merged)
