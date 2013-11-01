periscoped
==========

A daemon to download subtitles based on the great [periscope](https://github.com/patrickdessalle/periscope).


Installation
-------------
You will need periscope,  pyinotify, sqlite.

Installation via pip
```sh
pip  install periscope-daemon
```


Installation from the sources
```sh

python setup.py build
sudo python setup.py install
```

Availables commands
-------------------
First, you'll need to import your library
```sh
periscope-daemon --import ~/media/videos
```

Then, in a first console :

Start watching a folder for new video files
```sh
periscope-daemon --watch ~/media/videos
```

And in a second :
Start downloading subtitles
```sh
periscope-daemon --run
```

Purge the library
```sh
periscope-daemon --purge
```

Configuration
-------------

The main config file is located in ~/.config/periscope-daemon/daemon.conf
This file will override the default distributed configuration.

Availables configuration keys :
```
[DEFAULT]
# Laguages.
lang = fr,en
# How often the daemon should run, in minutes
run_each = 1
# When a subtitle is not found, the time to wait before re-processing the file will be multiplyed by this value
retry_factor = 3
```
