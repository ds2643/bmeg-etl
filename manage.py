#!/usr/bin/env python

import os
import argparse
import subprocess
from github import Github

REPO = "biostream"



def run_list(args):
    g = Github(os.environ["GITHUB_TOKEN"])
    for repo in g.get_organization(REPO).get_repos():
        print repo.name

def run_sync(args):
    g = Github(os.environ["GITHUB_TOKEN"])
    for repo in g.get_organization(REPO).get_repos():
        if repo.name.endswith("-extract") or repo.name.endswith("-transform") or repo.name.endswith("-schema"):
            print "Getting %s" % (repo.name)
            repo_dir = os.path.join(args.dir, repo.name)
            if not os.path.exists(repo_dir):
                subprocess.check_call("git clone --recursive %s" % (repo.clone_url), cwd=args.dir, shell=True)
            else:
                subprocess.check_call("git pull", shell=True, cwd=repo_dir)
            

    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    parser.add_argument("--dir", default="work")
    
    subparser = parser.add_subparsers()

    parser_list = subparser.add_parser("list")
    parser_list.set_defaults(func=run_list)

    parser_sync = subparser.add_parser("sync")
    parser_sync.set_defaults(func=run_sync)


    args = parser.parse_args()
    args.func(args)