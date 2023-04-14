from glob import glob
from multiprocessing import Process
from os import path, remove

from requests import get

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


class Updater:
    def __init__(self, settings):
        self.sett = settings
        self.downloads = set()

    def make_filepath(self, filename, tag, mod_id):
        dot_pos = filename.rfind('.')
        name = filename[:dot_pos] + "-" + tag + str(mod_id)
        filepath = self.sett['mods_path'] + name + filename[dot_pos:]
        return filepath, filename[dot_pos:]

    def _remove_old_file(self, filetype, tag, mod_id):
        old_file = glob(self.make_filepath("*" + filetype, tag, mod_id)[0])
        if old_file:
            remove(old_file[0])

    @staticmethod
    def _downloader(url, filename):
        file_stream = get(url, stream=True)
        with open(filename, 'wb+') as file:
            for chunk in file_stream.iter_content(1024):
                file.write(chunk)

    def download(self, *args):
        proc = Process(target=self._downloader, args=args)
        proc.start()
        self.downloads.add(proc)

    def wait_downloads(self):
        for dwnld in self.downloads:
            dwnld.join()


class CurseForgeUpdater(Updater):
    def _get_mod_info(self, mod_id):
        params = {'gameVersion': self.sett['game_ver'], 'pageSize': 1}
        req = get(f'https://api.curseforge.com/v1/mods/{mod_id}/files',
                  headers=self.HEADERS, params=params)
        return req.json()['data'][0]

    def _make_url(self, mod_id, file_info):
        if file_info['downloadUrl']:
            return file_info['downloadUrl']
        req = get(f'https://api.curseforge.com/v1/mods/{mod_id}',
                  headers=self.HEADERS)
        website = req.json()['data']['links']['websiteUrl']
        return f"{website}/download/{file_info['id']}/file"

    def __init__(self, settings):
        super().__init__(settings)
        self.HEADERS = {
            'Accept': 'application/json',
            'x-api-key': self.sett['curseforge']['key']
        }
        for mod_id in self.sett['curseforge']['mods_ids']:
            file_info = self._get_mod_info(mod_id)
            filepath, filetype = self.make_filepath(
                file_info['fileName'], 'c', mod_id)
            if not path.exists(filepath):
                self._remove_old_file(filetype, 'c', mod_id)
                url = self._make_url(mod_id, file_info)
                self.download(url, filepath)
        self.wait_downloads()


class GithubUpdater(Updater):
    @staticmethod
    def _base_checker(rules, rule_tag, check_obj):
        for rule in filter(lambda i: i[0] == rule_tag, rules):
            must_be = rule[1] == '+'
            word_there = rule[2:] in check_obj
            if word_there != must_be:
                return False
        return True

    def _check_release(self, release, rules):
        prerelease_ok = not release['prerelease'] or \
            self.sett['github']['use_prereleases']
        if not prerelease_ok:
            return False
        return self._base_checker(rules, 'r', release['name'])

    def __init__(self, settings):
        super().__init__(settings)
        repos = (i[0] for i in self.sett['github']['repos'])
        headers = {'Accept': "application/vnd.github+json"}
        params = {'per_page': 10}
        for repo_i, repo in enumerate(repos):
            repo_info = get(f"https://api.github.com/repos/{repo}/releases",
                            headers=headers, params=params).json()
            if 'message' in repo_info:
                print(repo_info['message'])
                return
            rules = self.sett['github']['repos'][repo_i][1]
            for release in repo_info:
                if self._check_release(release, rules):
                    for asset in release['assets']:
                        if self._base_checker(rules, 'a', asset['name']):
                            filepath, filetype = self.make_filepath(
                                asset['name'], 'g', repo_i)
                            if not path.exists(filepath):
                                self._remove_old_file(filetype, 'g', repo_i)
                                self.download(
                                    asset['browser_download_url'], filepath)
                            break
                    break
        self.wait_downloads()


if __name__ == '__main__':
    with open("settings.toml") as sett_file:
        sett = tomllib.loads(sett_file.read())
    if not path.exists(sett['mods_path']):
        raise FileNotFoundError("mods directory doesn't exists")
    modules = CurseForgeUpdater, GithubUpdater
    procs = (Process(target=m, args=(sett,)) for m in modules)
    for p in procs:
        p.start()
    for p in procs:
        p.join()
