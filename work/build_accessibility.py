"""Fetch checksum-verified official portable tools, then build the local helper APK."""
from pathlib import Path
import hashlib,json,urllib.request,zipfile,subprocess,shutil,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'work/android-tools';BUILD=ROOT/'work/android-build';SOURCE=ROOT/'android-helper'
TOOLS.mkdir(exist_ok=True);BUILD.mkdir(exist_ok=True)

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Rad.ai local build/0.1.13'}),timeout=90) as response:return response.read()

def download(url,name,digest,algorithm='sha256'):
    target=TOOLS/name
    if not target.exists() or hashlib.new(algorithm,target.read_bytes()).hexdigest()!=digest:
        print('Downloading',name,flush=True)
        with urllib.request.urlopen(url,timeout=120) as response,target.open('wb') as output:shutil.copyfileobj(response,output)
    if hashlib.new(algorithm,target.read_bytes()).hexdigest()!=digest:raise RuntimeError('Checksum mismatch: '+name)
    destination=TOOLS/target.stem;destination.mkdir(exist_ok=True)
    marker=destination/".verified-sha"
    if marker.exists() and marker.read_text()==digest:return destination
    with zipfile.ZipFile(target) as archive:
        for member in archive.infolist():
            if not (destination/member.filename).resolve().is_relative_to(destination.resolve()):raise ValueError('Unsafe archive entry')
        archive.extractall(destination)
    marker.write_text(digest)
    return destination

java_meta=json.loads(fetch('https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows'))[0]['binary']['package']
java_root=download(java_meta['link'],'temurin21.zip',java_meta['checksum'])
JDK=next(java_root.glob('*/bin/java.exe')).parent
repository=ET.fromstring(fetch('https://dl.google.com/android/repository/repository2-1.xml'))

def sdk(path,name):
    package=next(p for p in repository.iter('remotePackage') if p.get('path')==path)
    archives=package.find('archives').findall('archive')
    archive=next(a for a in archives if a.findtext('host-os') in (None,'windows'))
    complete=archive.find('complete');checksum=complete.find('checksum')
    return download('https://dl.google.com/android/repository/'+complete.findtext('url'),name,checksum.text,'sha1')

build_tools=sdk('build-tools;35.0.0','build-tools35.zip')
platform=sdk('platforms;android-35','platform35.zip')
AAPT=next(build_tools.rglob('aapt2.exe'));BT=AAPT.parent;ANDROID=next(platform.rglob('android.jar'))

def run(*args):subprocess.run([str(a) for a in args],check=True,cwd=BUILD)

generated=BUILD/'generated';classes=BUILD/'classes';dex=BUILD/'dex'
for directory in (generated,classes,dex):directory.mkdir(exist_ok=True)
run(AAPT,'compile','--dir',SOURCE/'res','-o',BUILD/'resources.zip')
run(AAPT,'link','--manifest',SOURCE/'AndroidManifest.xml','-I',ANDROID,'--java',generated,
    '-o',BUILD/'base.apk',BUILD/'resources.zip')
sources=list((SOURCE/'src').rglob('*.java'))+list(generated.rglob('*.java'))
run(JDK/'javac.exe','-encoding','UTF-8','-source','8','-target','8','-classpath',ANDROID,'-d',classes,*sources)
run(JDK/'jar.exe','cf',BUILD/'classes.jar','-C',classes,'.')
run(JDK/'java.exe','-cp',BT/'lib/d8.jar','com.android.tools.r8.D8','--lib',ANDROID,'--min-api','26','--output',dex,BUILD/'classes.jar')
shutil.copy2(BUILD/'base.apk',BUILD/'unsigned.apk')
with zipfile.ZipFile(BUILD/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as archive:archive.write(dex/'classes.dex','classes.dex')
run(BT/'zipalign.exe','-f','4',BUILD/'unsigned.apk',BUILD/'aligned.apk')
key=ROOT/'runtime/rad-android-debug.jks';key.parent.mkdir(exist_ok=True)
if not key.exists():run(JDK/'keytool.exe','-genkeypair','-keystore',key,'-alias','raddebug','-storepass','android','-keypass','android',
                       '-keyalg','RSA','-keysize','2048','-validity','10000','-dname','CN=Rad.ai Local Development')
out=SOURCE/'rad-bridge.apk'
run(JDK/'java.exe','-jar',BT/'lib/apksigner.jar','sign','--ks',key,'--ks-key-alias','raddebug','--ks-pass','pass:android','--out',out,BUILD/'aligned.apk')
run(JDK/'java.exe','-jar',BT/'lib/apksigner.jar','verify','--verbose',out)
print('Built helper:',out,flush=True)
