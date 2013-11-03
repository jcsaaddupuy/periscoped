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
$ periscope-daemon --import ~/media/videos
# You can also import multiples path in a one shot !
$ periscope-daemon --import ~/media/videos1 --import ~/media/videos2 --import ~/media/videosN

```

Then, in a first console :

Start watching a folder for new video files
```sh
$ periscope-daemon --watch ~/media/videos
# You can also watch multiples path in a one shot !
$ periscope-daemon --watch ~/media/videos1 --watch ~/media/videos2 --watch ~/media/videosN
```

And in a second :
Start downloading subtitles
```sh
$ periscope-daemon --run
```

Purge the library (removes deleted files on the filesystem from local database)
```sh
$ periscope-daemon --purge
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
# The value will be interpreted as an integer
run_each = 1
# When a subtitle is not found, the time to wait before re-processing the file will be multiplyed by this value
# The value will be interpreted as a float
retry_factor = 3
```


Init scritps
-------------
There are init script for debian based distribution.

You must copy init/debian/init.d/periscope-daemon to /etc/init.d

You must copy init/debian/default/periscope-daemon to /etc/default

You will have to modify WATCHED_DIR in /etc/init.d/periscope-daemon and USER in /etc/init.d/periscope-daemon.


You will then be able to start/stop/restart/... it as a daemon :

```sh
# /etc/init.d/periscope-daemon start
```

And watch for the log in /var/log/periscope-daemon/daemon.log:
```sh
$ tail -f /var/log/periscope-daemon/daemon.log
```

