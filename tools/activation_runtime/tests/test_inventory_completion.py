"""Objective inventory acceptance fixtures cannot replace the real GitHub source."""
from copy import deepcopy
from hashlib import sha1,sha256
from pathlib import Path
import tempfile
import unittest
from tools.activation_runtime.common import fingerprint
from tools.activation_runtime.inventory_completion import verify,KIND,REPO,WORKFLOW,REQUIRED_STEPS


class InventoryCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        source=self.root/'tools/activation_runtime/audit.py';source.parent.mkdir(parents=True);source.write_bytes(b'fixture inventory source\n')
        workflow=self.root/WORKFLOW;workflow.parent.mkdir(parents=True);workflow.write_bytes(b'fixture workflow\n')
        modules=[{"path":"tools/activation_runtime/audit.py","sha256":sha256(source.read_bytes()).hexdigest()}]
        self.item={"story_id":"US-001","implementation_commit":"1"*40,"acceptance_sha256":"a"*64,"modules":modules,
            "branch":"work","base_commit":"2"*40,"remaining":"No domain truth claimed","test_or_receipt":"tests",
            "criteria":[{"number":i,"acceptance":"MET_OBSERVED_SOURCE_AND_CI"} for i in range(1,5)]}
        self.item['completion_evidence']={"kind":KIND,"repository":REPO,"implementation_commit":"1"*40,
            "module_inventory_sha256":fingerprint(modules),"acceptance_sha256":"a"*64,"workflow_run_id":123,
            "url":"https://github.com/"+REPO+"/actions/runs/123"}
        self.inventory={"stories":[self.item,{"story_id":"US-022","status":"BLOCKED","branch":"work","base_commit":"2"*40,"test_or_receipt":"tests","remaining":"PR review"}],
            "implementation_boundaries":{"canonical_ff_rct_decoder":"UNAVAILABLE","independent_domain_admission":"NOT_ESTABLISHED","reference_scene_decoder":"AVAILABLE_RESEARCH_REFERENCE"}}
        self.responses={"/actions/runs/123":{"head_sha":"1"*40,"status":"completed","conclusion":"success","event":"push","path":WORKFLOW,
            "repository":{"full_name":REPO},"head_repository":{"full_name":REPO}},
            "/actions/runs/123/jobs?per_page=100":{"jobs":[{"name":"bounded-activation","conclusion":"success","steps":[{"name":name,"conclusion":"success"} for name in sorted(REQUIRED_STEPS)]}]},
            "/git/trees/"+"1"*40+"?recursive=1":{"truncated":False,"tree":[{"path":str(path.relative_to(self.root)),"type":"blob","sha":sha1(b'blob '+str(len(path.read_bytes())).encode()+b'\0'+path.read_bytes()).hexdigest()} for path in (source,workflow)]},
            "/pulls/69":{"merged":False}}

    def check(self):return verify(self.item,self.inventory,self.root,_fetch=lambda path:deepcopy(self.responses[path]))

    def test_actual_source_ci_and_open_baseline_have_inventory_only_acceptance(self):
        row=self.check();self.assertEqual(row['scope'],'SOURCE_INVENTORY_SOFTWARE_ONLY')
        self.assertEqual(row['pr_69'],'IN_REVIEW');self.assertEqual(row['independent_domain_validation'],'NOT_ESTABLISHED')

    def test_objective_path_cannot_complete_other_stories(self):
        self.item['story_id']='US-002'
        with self.assertRaises(ValueError):self.check()

    def test_forged_scope_link_commit_and_criteria_bindings_refuse(self):
        original=deepcopy(self.item['completion_evidence'])
        for key,value in (('url','https://elsewhere.invalid/pass'),('workflow_run_id',True),('implementation_commit','0'*40),
                          ('repository','other/repo'),('acceptance_sha256','0'*64),('module_inventory_sha256','0'*64)):
            self.item['completion_evidence']={**original,key:value}
            with self.assertRaises(ValueError):self.check()

    def test_failed_pending_fork_or_different_workflow_run_refuses(self):
        original=deepcopy(self.responses['/actions/runs/123'])
        for changes in ({'conclusion':'failure'},{'status':'in_progress'},{'head_sha':'3'*40},{'event':'pull_request'},
                        {'path':'.github/workflows/other.yml'},{'head_repository':{'full_name':'other/repo'}}):
            self.responses['/actions/runs/123']={**original,**changes}
            with self.assertRaises(ValueError):self.check()

    def test_skipped_missing_or_duplicate_ci_jobs_refuse(self):
        key='/actions/runs/123/jobs?per_page=100';original=deepcopy(self.responses[key])
        self.responses[key]['jobs'][0]['steps'][0]['conclusion']='skipped'
        with self.assertRaises(ValueError):self.check()
        self.responses[key]=deepcopy(original);self.responses[key]['jobs'][0]['steps'].pop()
        with self.assertRaises(ValueError):self.check()
        self.responses[key]=deepcopy(original);self.responses[key]['jobs']*=2
        with self.assertRaises(ValueError):self.check()

    def test_immutable_tree_mismatch_or_truncation_refuses(self):
        key='/git/trees/'+'1'*40+'?recursive=1';original=deepcopy(self.responses[key])
        self.responses[key]['truncated']=True
        with self.assertRaises(ValueError):self.check()
        self.responses[key]=original;self.responses[key]['tree'][0]['sha']='0'*40
        with self.assertRaises(ValueError):self.check()

    def test_altered_or_missing_local_source_cannot_borrow_passing_ci(self):
        path=self.root/'tools/activation_runtime/audit.py';path.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.check()
        path.unlink()
        with self.assertRaises(ValueError):self.check()

    def test_open_pr_cannot_satisfy_baseline_story_merge_requirement(self):
        self.inventory['stories'][1]['status']='DONE'
        with self.assertRaises(ValueError):self.check()
        self.responses['/pulls/69']['merged']=True
        self.assertEqual(self.check()['pr_69'],'MERGED')

    def test_limits_inventory_and_all_criteria_must_be_explicit(self):
        original=deepcopy(self.inventory['implementation_boundaries'])
        self.inventory['implementation_boundaries']['independent_domain_admission']='ADMIT'
        with self.assertRaises(ValueError):self.check()
        self.inventory['implementation_boundaries']=original;self.item['criteria'][0]['acceptance']='PENDING'
        with self.assertRaises(ValueError):self.check()
        self.item['criteria'][0]['acceptance']='MET_OBSERVED_SOURCE_AND_CI';self.item['test_or_receipt']=''
        with self.assertRaises(ValueError):self.check()

    def test_unavailable_external_evidence_never_turns_into_acceptance(self):
        def unavailable(path):raise ValueError('Source unavailable')
        with self.assertRaises(ValueError):verify(self.item,self.inventory,self.root,_fetch=unavailable)
