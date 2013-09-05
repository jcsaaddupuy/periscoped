periscoped
==========

A daemon to download subtitles based on the great [periscope](https://github.com/patrickdessalle/periscope).


Installation
-------------
You will need periscope,  pyinotify, sqlite.

```sh

python setup.py build
sudo python setup.py install
cp config/periscoped ~/.config/periscope
```

Availables commands
-------------------
First, you'll need to import your library
```sh
periscoped.py --import ~/media/videos
```

Then, in a first console :

Start watching a folder for new video files
```sh
periscoped.py --run
```

And in a second :
Start downloading subtitles
```sh
periscoped.py --run
```

Purge the library
```sh
periscoped.py --purge
```

Configuration
-------------

The main config file is located in ~/.config/periscope/periscoped.
Availables configuration keys :
```
[DEFAULT]
# Laguages. If not found, will fallback on periscope config.
lang = fr,en
# How often the daemon should run, in minutes
run_each = 1
# When a subtitle is not found, the time to wait before re-processing the file will be multiplyed by this value
retry_factor = 3
```
