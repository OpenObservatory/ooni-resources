This repository is used to host the URL lists and resources used by ooni-probe
and measurement-kit and to handle the update of them.

## Maintainer usage

If this is the first time you are running this you may have to initialize your
working_dir and the remote repository.

This can be done with:

```
python run.py initialize
```

Every time you need to check for updates of the resources you should run:

```
python run.py update
```
