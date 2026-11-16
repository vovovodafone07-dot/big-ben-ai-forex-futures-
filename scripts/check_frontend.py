"""Check inline dashboard JavaScript without starting a browser."""
from html.parser import HTMLParser
from pathlib import Path
import os
import subprocess

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture=False
        self.code=[]
    def handle_starttag(self,tag,attrs):
        if tag=="script":
            self.capture="src" not in dict(attrs)
    def handle_endtag(self,tag):
        if tag=="script":self.capture=False
    def handle_data(self,data):
        if self.capture and data.strip():self.code.append(data)

parser=Scripts()
parser.feed((Path(__file__).resolve().parents[1]/"platform"/"index.html").read_text(encoding="utf-8"))
for number,code in enumerate(parser.code,1):
    subprocess.run([os.getenv("NODE_BINARY","node"),"--check","--input-type=commonjs"],input=code.encode("utf-8"),check=True,timeout=15)
print("Checked "+str(len(parser.code))+" inline JavaScript blocks")
subprocess.run([os.getenv("NODE_BINARY","node"),str(Path(__file__).with_name("test_symbol_selection.cjs"))],check=True,timeout=15)
