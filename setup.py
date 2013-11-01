from setuptools import setup, find_packages
import version

PACKAGE = 'periscope-daemon'

setup(name = PACKAGE, version = version.VERSION,
    license = "WTFPL",
    description = "Python daemon to download automagically subtitles. Build on top of the great periscope (https://github.com/patrickdessalle/periscope)",
    author = "Jean-Christophe Saad-Dupuy",
    author_email = "saad.dupuy@gmail.com",
    url = "https://github.com/jcsaaddupuy/periscoped",
    packages = find_packages('src'),
    package_dir = {'':'src'},   # tell distutils packages are under src
    include_package_data = True,
    package_data = {
      '':['config/*.conf']
      },
    entry_points = {
      'console_scripts': [
        'periscope-daemon = periscope_daemon:main',
        ]
      },
    install_requires = ["periscope >= dev", "pyinotify >= 0.9.4" ]
    )
