from setuptools import setup
import version

PACKAGE = 'periscoped'

setup(name = PACKAGE, version = version.VERSION,
    license = "WTFPL",
    description = "Python daemon to download automagically subtitles. build on top of the great periscope (https://github.com/patrickdessalle/periscope)",
    author = "Jean-Christophe Saad-Dupuy",
    author_email = "saad.dupuy@gmail.com",
    url = "https://github.com/jcsaaddupuy/periscoped",
    scripts = [ "bin/periscoped.py" ],
    install_requires = ["periscope >= dev"]
    )
