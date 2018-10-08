# Module returning last modification time on files import

import os
import sys

mtimes = {}

if int(sys.version[0]) < 2:

    python_path_hook = sys.path_hooks[1]

    def mtimes_path_hook(*args, **kwargs):
        r = python_path_hook(*args, **kwargs)
        new_loaders = []
        for extension, loader in r._loaders:
            if hasattr(loader, 'path_stats'):

                class MyLoader(loader):

                    def path_stats(self, path):
                        r = super().path_stats(path)
                        mtimes[path] = r['mtime']
                        return r

                new_loaders.append((extension, MyLoader))
            else:
                new_loaders.append((extension, loader))
        r._loaders = new_loaders
        return r

    sys.path_hooks[1] = mtimes_path_hook


    def get(path):
        return mtimes[path]

else:
    def get(path):
        return os.path.getmtime(path)