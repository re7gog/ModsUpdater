from concurrent.futures import ThreadPoolExecutor
from glob import glob
from multiprocessing import Process
from os import path, remove
from urllib.parse import unquote

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from requests import get


class Updater:
    def __init__(self, settings):
        self.settings = settings

    def _make_filepath(self, filename, tag, mod_id):
        dot_pos = filename.rfind('.')
        name = filename[:dot_pos] + "-" + tag + str(mod_id)
        filepath = self.settings['mods_path'] + name + filename[dot_pos:]
        return filepath, filename[dot_pos:]

    @staticmethod
    def _downloader(args):
        file_stream = get(args[0], stream=True)
        with open(args[1], 'wb') as file:
            for chunk in file_stream.iter_content(1024):
                file.write(chunk)

    def download(self, downloads):
        with ThreadPoolExecutor(max_workers=len(downloads)) as executor:
            executor.map(self._downloader, downloads)


class CurseForgeUpdater(Updater):
    def _get_mod_info(self, mod_id):
        headers = {
            'Accept': 'application/json',
            'x-api-key': self.settings['curseforge']['key']
        }
        params = {'gameVersion': self.settings['game_ver'], 'pageSize': 1}
        req = get(f'https://api.curseforge.com/v1/mods/{mod_id}/files',
                  headers=headers, params=params)
        return req.json()['data'][0]

    def __init__(self, settings):
        super().__init__(settings)
        downloads = set()
        for mod_id in self.settings['curseforge']['mods_ids']:
            file_info = self._get_mod_info(mod_id)
            filepath, filetype = self._make_filepath(
                file_info['fileName'], 'c', mod_id)
            if not path.exists(filepath):
                old_file = glob(self._make_filepath(
                    "*" + filetype, 'c', mod_id)[0])
                if old_file:
                    remove(old_file[0])
                downloads.add((file_info['downloadUrl'], filepath))
        if downloads:
            self.download(downloads)


class GithubUpdater(Updater):
    def _check(self, repo, ver):
        release = not ver['prerelease'] or \
            ver['prerelease'] and self.settings['github']['use_prereleases']
        game_ver = not self.settings['github']['repos'][repo][1] or \
            self.settings['game_ver'] in ver['name']
        return release and game_ver

    def __init__(self, settings):
        super().__init__(settings)
        repos = (i[0] for i in self.settings['github']['repos'])
        headers = {'Accept': "application/vnd.github+json"}
        downloads = set()
        for repo_i, repo in enumerate(repos):
            repo_info = get(f"https://api.github.com/repos/{repo}/releases",
                            headers=headers).json()
            if 'message' in repo_info:
                print(repo_info['message'])
                return
            for ver in repo_info:
                if self._check(repo_i, ver):
                    url = ver['assets'][-1]['browser_download_url']
                    file_name = unquote(url[url.rfind("/") + 1:])
                    filepath, filetype = self._make_filepath(
                        file_name, 'g', repo_i)
                    if not path.exists(filepath):
                        old_file = glob(self._make_filepath(
                            "*" + filetype, 'g', repo_i)[0])
                        if old_file:
                            remove(old_file[0])
                        downloads.add((url, filepath))
                    break
        if downloads:
            self.download(downloads)


if __name__ == '__main__':
    with open("settings.toml") as sett_file:
        sett = tomllib.loads(sett_file.read())
    p1 = Process(target=CurseForgeUpdater, args=(sett,))
    p1.start()
    p2 = Process(target=GithubUpdater, args=(sett,))
    p2.start()
    p2.join()
    p1.join()
