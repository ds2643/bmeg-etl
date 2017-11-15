#!/usr/bin/env python

import re
import os
import yaml
import argparse
import subprocess
import logging
import shutil
import json
from glob import glob
#from github import Github
import cwlgen
from cwlgen.import_cwl import CWLToolParser
from cwlgen.workflow import Workflow, WorkflowStep, WorkflowStepInput, InputParameter, WorkflowOutputParameter

REPO = "biostream"

def run_list(args):
    g = Github(os.environ["GITHUB_TOKEN"])
    for repo in g.get_organization(REPO).get_repos():
        print repo.name

def run_sync(args):
    g = Github(os.environ["GITHUB_TOKEN"])
    for repo in g.get_organization(REPO).get_repos():
        if repo.name.endswith("-extract") or repo.name.endswith("-transform") or repo.name.endswith("-schema"):
            logging.info("Getting %s" % (repo.name))
            repo_dir = os.path.join(args.dir, repo.name)
            if not os.path.exists(repo_dir):
                subprocess.check_call("git clone --recursive %s" % (repo.clone_url), cwd=args.dir, shell=True)
            else:
                subprocess.check_call("git pull", shell=True, cwd=repo_dir)


def map_files(path, base=[]):
    out = {}
    if os.path.isdir(path):
        for i in glob(os.path.join(path, "*")):
            for k, v in map_files(i, base + [os.path.basename(i)]).items():
                out[k] = v
        return out
    else:
        return {os.path.join(*base) : {"class" : "File", "path" : os.path.abspath(path)}}


RE_GITHUB = re.compile(r'^(github.com)/([^/]+)/([^/]+)/(.*)$')

def run_compile(args):
    with open(args.processes) as handle:
        txt = handle.read()
        config = yaml.load(txt)

    """
    Load all tools
    """
    for proc in config:
        #print proc['command']
        res = RE_GITHUB.search(proc['command'])
        if res:
            g = res.groups()
            src_dir = os.path.abspath(os.path.join(args.dir, g[0], g[1], g[2]))
            parent_dir = os.path.dirname(src_dir)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir)
            if not os.path.exists(src_dir):
                logging.info("Downloading: %s" % src_dir)
                clone_url = "https://%s/%s/%s.git" % (g[0], g[1], g[2])
                subprocess.check_call("git clone --recursive %s" % (clone_url), cwd=parent_dir, shell=True)

    tools = {}
    tool_pathmap = {}
    for proc in config:
        tool_path = os.path.abspath(os.path.join(args.dir, proc['command']))
        if os.path.exists(tool_path):
            logging.info("Loading %s " % tool_path)
            if tool_path not in tools:
                parser = CWLToolParser()
                tools[proc['command']] = parser.import_cwl(tool_path)
                tool_pathmap[proc['command']] = tool_path
        else:
            logging.error("missing %s" % tool_path)

    #the object store map
    data_map = map_files(args.data)
    #the workflow output map
    output_map = {}
    #the jobs to be done
    jobs = {}
    #results map
    results = {}
    added = True
    while added:
        added = False
        for proc in config:
            if proc['key'] not in jobs:
                imap = {}
                for k, v in proc.get('inputs', {}).items():
                    if v in data_map:
                        imap[k] = data_map[v]
                    if v in output_map:
                        imap[k] = output_map[v]

                if len(imap) == len(proc.get('inputs', {})):
                    var = {}
                    for k, v in proc.get("vars", {}).items():
                        var[k] = v

                    logging.info("Adding %s" % (proc['key']))

                    outs = {}
                    needed = False
                    for k, v in proc['outputs'].items():
                        if v not in data_map:
                            out_name = "%s_%s" % (proc['key'], k)
                            out_path = "%s/%s" % (proc['key'], k)
                            #data_map[v] = "%s/%s" % (proc['key'], k)
                            outs[out_name] = k
                            output_map[v] = out_path

                            results[out_name] = v
                            needed = True

                    if needed:
                        jobs[proc['key']] = {'run' : tool_pathmap[proc['command']], "inputs" : imap, "vars" : var, "outputs" : outs}
                        added = True

    out = Workflow()
    out_job = {}
    out_map = {}
    out_input = {}
    for k, v in jobs.items():
        step = WorkflowStep(id=k, run=v['run'])
        for i, j in v['inputs'].items():
            if isinstance(j, basestring):
                step.inputs.append(WorkflowStepInput(i, src=j))
            else:
                input_name = "%s_%s" % (k,i)
                out_input[input_name] = j
                out.inputs.append( InputParameter(input_name, param_type="File") )
                step.inputs.append(WorkflowStepInput(i, src=input_name))

        for i, j in v['vars'].items():
            step.inputs.append(WorkflowStepInput(i, default=j))

        for i, j in v['outputs'].items():
            step.outputs.append(j)
            name = "%s_%s" % (k, j)
            src = "%s/%s" % (k, j)
            out.outputs.append(WorkflowOutputParameter(i, outputSource=src, param_type="File"))
            out_map[name] = results[name]
        out.steps.append(step)

    out.export(args.out + ".cwl")
    with open(args.out + ".outmap", "w") as handle:
        handle.write(json.dumps(out_map, indent=4))
    with open(args.out + ".inputs", "w") as handle:
        handle.write(json.dumps(out_input, indent=4))

def run_store(args):
    with open(args.outmap) as handle:
        outmap = json.loads(handle.read())

    with open(args.cwlout) as handle:
        cwlout = json.loads(handle.read())

    for k, v in cwlout.items():
        outpath = os.path.join(args.data, outmap[k])
        if not os.path.exists(os.path.dirname(outpath)):
            os.makedirs(os.path.dirname(outpath))
        shutil.copy(v['path'], outpath)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--dir", default="src")

    subparser = parser.add_subparsers()

    parser_list = subparser.add_parser("list")
    parser_list.set_defaults(func=run_list)

    parser_sync = subparser.add_parser("sync")
    parser_sync.set_defaults(func=run_sync)

    parser_compile = subparser.add_parser("compile")
    parser_compile.add_argument("--data", default="data")
    parser_compile.add_argument("--out", default="out")
    parser_compile.add_argument("processes")
    parser_compile.set_defaults(func=run_compile)

    parser_store = subparser.add_parser("store")
    parser_store.add_argument("--data", default="data")
    parser_store.add_argument("outmap")
    parser_store.add_argument("cwlout")
    parser_store.set_defaults(func=run_store)

    args = parser.parse_args()
    args.func(args)
