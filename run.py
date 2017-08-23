import os
import json
import shutil
import hashlib
import argparse
from datetime import datetime
from glob import glob

import git
import requests

TESTING = True if os.getenv('OONI_RESOURCES_TESTING') else False

GEOIP_ASN_URL = "https://download.maxmind.com/download/geoip/database/asnum/GeoIPASNum.dat.gz"
GEOIP_ASN_FILE = "working_dir/GeoIPASNum.dat.gz"

GEOIP_URL = "https://geolite.maxmind.com/download/geoip/database/GeoLiteCountry/GeoIP.dat.gz"
GEOIP_FILE = "working_dir/GeoIP.dat.gz"

CITIZENLAB_TEST_LISTS_REPO_URL = "https://github.com/citizenlab/test-lists.git"
CITIZENLAB_TEST_LISTS_REPO = "working_dir/test-lists/"
CITIZENLAB_TEST_LISTS = "working_dir/test-lists/lists/*.csv"
BRIDGE_REACHABILITY_LISTS = "bridge_reachability/*.csv"

CWD = os.path.dirname(__file__)
MANIFEST_FILE = "assets/manifest.json"

try:
    GITHUB_TOKEN = open("GITHUB_TOKEN").read().strip()
except Exception:
    print("You must write your github token to a file called \"GITHUB_TOKEN\"")
    raise

RESOURCES = [
    {"maxmind-geoip": [GEOIP_ASN_FILE, GEOIP_FILE]},
    {"citizenlab-test-lists": [CITIZENLAB_TEST_LISTS]},
    {"tor-bridges": [BRIDGE_REACHABILITY_LISTS]}
]

GH_BASE_URL = "https://api.github.com/repos/OpenObservatory/ooni-resources"
if TESTING:
    GH_BASE_URL = "https://api.github.com/repos/OpenObservatory/ooni-resources.testing"

REMOTE = "origin"
if TESTING:
    REMOTE = "testing"

def _get_latest_release_tag():
    params = {
        "access_token": GITHUB_TOKEN
    }
    r = requests.get(GH_BASE_URL + "/releases/latest",
                    params=params)
    return r.json()['tag_name']


def _create_latest_version():
    params = {
        "access_token": GITHUB_TOKEN
    }
    data = {
        "tag_name": "latest",
        "target_commitish": "master",
        "name": "latest",
        "body": "This tag is used to obtain the latest version of resources",
        "draft": False,
        "prerelease": False
    }
    r = requests.post(GH_BASE_URL + "/releases",
                     params=params, json=data)
    try:
        assert r.status_code == 201
    except:
        print r.text
        raise
    return r.json()["id"]

def _upload_asset(upload_url, name, content_type, data):
    headers = {
        "Content-Type": content_type
    }
    params = {
        "access_token": GITHUB_TOKEN,
        "name": name
    }
    print("Uploading asset {0}".format(params["name"]))
    print("to: {0}".format(upload_url))
    r = requests.post(upload_url,
                      params=params,
                      headers=headers,
                      data=data)
    if r.status_code != 201:
        print(r.text)
        raise Exception("Could not upload asset")
    return r.json()

def _delete_all_assets(release_id):
    params = {
        "access_token": GITHUB_TOKEN,
    }
    r = requests.get(GH_BASE_URL + "/releases/{0}/assets".format(release_id),
                     params=params)
    for asset in r.json():
        requests.delete(GH_BASE_URL + "/releases/assets/{0}".format(asset["id"]),
                        params=params)
        assert r.status_code/100 == 2

def update_latest_version(tag_name):
    params = {
        "access_token": GITHUB_TOKEN
    }
    r = requests.get(GH_BASE_URL + "/releases/tags/latest",
                     params=params)
    if r.status_code == 404:
        release_id = _create_latest_version()
    elif r.status_code == 200:
        release_id = r.json()["id"]

    data = {
        "target_commitish": "master"
    }
    r = requests.patch(GH_BASE_URL + "/releases/{0}".format(release_id),
                       params=params, json=data)
    assert r.status_code == 200

    upload_url = r.json()['upload_url'].replace("{?name,label}", "")
    _delete_all_assets(release_id)
    _upload_asset(upload_url, "version", "text/plain", tag_name)

def create_new_release(tag_name):
    params = {
        "access_token": GITHUB_TOKEN
    }
    data = {
        "tag_name": tag_name,
        "target_commitish": "master",
        "name": tag_name,
        "body": "Update for ooni-resources {0}".format(
            datetime.now().strftime("%Y-%m-%d")
        ),
        "draft": False,
        "prerelease": False
    }
    r = requests.post(GH_BASE_URL + "/releases",
                      params=params, json=data)
    try:
        assert r.status_code == 201
    except:
        print r.text
        return
    j = r.json()
    upload_url = j["upload_url"].replace("{?name,label}", "")
    for asset in glob("assets/*"):
        if asset.endswith(".csv"):
            content_type = "text/csv"
        elif asset.endswith(".gz"):
            content_type = "application/gzip"
        data = open(asset, "r").read()
        _upload_asset(upload_url,
                      name=os.path.basename(asset),
                      content_type=content_type,
                      data=data)
    update_latest_version(tag_name)

def _resolve_asset_dst(path):
    """
    We write assets to their path by replacing / with .
    """
    return os.path.join("assets", path.replace("/", "."))

def _resolve_path(path):
    """
    Resolves a path in the manifest to a path relative to the working
    directory.
    """
    prepath, filename = path.split("/")
    if prepath == "citizenlab-test-lists":
        real_prepath = "working_dir/test-lists/lists/"
    elif prepath == "maxmind-geoip":
        real_prepath = "working_dir/"
    elif prepath == "tor-bridges":
        real_prepath = "bridge_reachability"
    else:
        raise Exception("Invalid prepath")
    return os.path.join(real_prepath, filename)

def _list_resources():
    return [
        (name, filename)
            for resource in RESOURCES
            for name, file_globs in resource.items()
            for file_glob in file_globs
            for filename in glob(file_glob)
    ]

def download_file(url, dst):
    print("Downloading %s" % url)
    r = requests.get(url, stream=True)
    with open(dst, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    return dst

def sha256_sum(path):
    h = hashlib.sha256()
    with open(path) as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def _format_resource(prepath, filepath):
    filename = os.path.basename(filepath)
    path = "{0}/{1}".format(prepath, filename)
    country_code = "ALL"
    if prepath == "citizenlab-test-lists":
        cc = filename.split(".")[0]
        if len(cc) == 2:
            country_code = cc.upper()
    sha256 = sha256_sum(filepath)
    return {
        "path": path,
        "sha256": sha256,
        "version": 0,
        "country_code": country_code
    }


def write_manifest(manifest):
    with open(MANIFEST_FILE, "wb") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

def _initialize_test_lists():
    # Git clone etc.
    if os.path.exists(CITIZENLAB_TEST_LISTS_REPO):
        print("Repo already exists. Skipping.")
        return
    git.Repo.clone_from(CITIZENLAB_TEST_LISTS_REPO_URL,
                        CITIZENLAB_TEST_LISTS_REPO,
                        branch="master")

def _initialize_geoip():
    if not os.path.exists(GEOIP_ASN_FILE):
        download_file(GEOIP_ASN_URL, GEOIP_ASN_FILE)
    if not os.path.exists(GEOIP_FILE):
        download_file(GEOIP_URL, GEOIP_FILE)

def initialize(args):
    resources = []
    _initialize_geoip()
    _initialize_test_lists()

    for name, filepath in _list_resources():
        resources.append(_format_resource(name, filepath))

    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE) as f:
            manifest = json.load(f)
    else:
        manifest = {
            "version": 1
        }

    manifest["resources"] = resources

    copy_assets(resources)
    write_manifest(manifest)
    update_repo(manifest["version"])

def _update_test_lists():
    repo = git.Repo(CITIZENLAB_TEST_LISTS_REPO)
    repo.remotes.origin.pull()

def update_repo(version):
    print("Updating the repo")
    repo = git.Repo(CWD)
    repo.git.add("assets/")
    if repo.is_dirty():
        repo.git.commit("-a", m="Automatic update")
        print("Pushing changes to remote")
        repo.git.push("-u", "origin", "master")
    print("Creating a new release with version {0}".format(version))
    create_new_release(str(version))

def copy_assets(resources):
    print("Copying assets")
    for resource in resources:
        shutil.copy(_resolve_path(resource['path']),
                    _resolve_asset_dst(resource['path']))

def update(args):
    print("Updating manifest")
    if args.no_push:
        print(" - will not push to remote")
    changed = False
    with open(MANIFEST_FILE) as f:
        manifest = json.load(f)

    _update_test_lists()

    resource_paths = set(["{0}/{1}".format(name, os.path.basename(path))
                          for (name, path) in _list_resources()])
    manifest_paths = set([resource['path']
                          for resource in manifest['resources']])

    # Check for changed paths
    for resource in manifest['resources']:
        if resource['path'] not in resource_paths:
            print("Removing %s from manifest" % resource['path'])
            manifest['resources'].remove(resource)
            changed = True
            continue
        new_hash = sha256_sum(_resolve_path(resource['path']))
        if new_hash != resource["sha256"]:
            changed = True
            resource["sha256"] = new_hash
            resource["version"] += 1

    # Add the new resource paths
    new_paths = resource_paths - manifest_paths
    for new_path in new_paths:
        prepath = new_path.split("/")[0]
        filepath = _resolve_path(new_path)
        manifest['resources'].append(_format_resource(prepath, filepath))

    if changed:
        manifest['version'] += 1
        write_manifest(manifest)
        copy_assets(manifest['resources'])
        if not args.no_push:
            update_repo(manifest['version'])
    else:
        print("No update required")

    return changed

def parse_args():
    if TESTING:
        print("WE ARE IN TESTING")
    parser = argparse.ArgumentParser(description="Handle the workflow for updating ooni resources")
    subparsers = parser.add_subparsers()

    parser_update = subparsers.add_parser("update")
    parser_update.add_argument('--no-push', action='store_true')
    parser_update.set_defaults(func=update)

    parser_initialize= subparsers.add_parser("initialize")
    parser_initialize.set_defaults(func=initialize)

    args = parser.parse_args()
    args.func(args)

def main():
    parse_args()

if __name__ == "__main__":
    main()
