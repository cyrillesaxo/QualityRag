"""US-002 version, uniqueness, offline-reference and acceptance rejection checks."""
from copy import deepcopy
from hashlib import sha1,sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from tools.activation_runtime import contracts
from tools.activation_runtime.common import canonical,fingerprint
from tools.activation_runtime.schema_completion import verify,KIND,STEP
import test_inventory_completion as fixtures


class SchemaCatalogTests(unittest.TestCase):
    def test_all_catalog_members_fixtures_roundtrip_and_rejection_witnesses(self):
        report=contracts.catalog_report();self.assertEqual(report,contracts.catalog_report())
        self.assertEqual(report['schema_count'],len(contracts.NAMES))
        self.assertEqual(set(report['rejection_witnesses']),{'duplicate_node_id','unknown_operator','invalid_type','oversize_payload','incompatible_major'})
        self.assertTrue(all(row['result']=='REJECTED' for row in report['rejection_witnesses'].values()))
        self.assertFalse(report['can_generate'])

    def test_duplicate_ids_are_rejected_by_the_public_validator(self):
        base=Path(contracts.__file__).with_name('fixtures')
        for name in ('packspec','observation-graph'):
            value=json.loads((base/(name+'.json')).read_text());value['nodes'].append(deepcopy(value['nodes'][0]))
            with self.assertRaisesRegex(ValueError,'Duplicate node'):contracts.validate(name,value)

    def test_remote_refs_dynamic_refs_and_nested_bases_never_retrieve_network_content(self):
        schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://qualityrag.local/schemas/source/v1.0','type':'object'}
        with tempfile.TemporaryDirectory() as directory,patch.object(contracts,'CATALOG',Path(directory)),patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            for change in ({'$ref':'https://example.invalid/schema'},{'$dynamicRef':'file:///outside'}, {'properties':{'x':{'$id':'https://example.invalid/'}}}):
                (Path(directory)/'source.json').write_text(json.dumps({**schema,**change}))
                with self.assertRaises(ValueError):contracts.load_schema('source')

    def test_local_refs_work_but_wrong_namespace_major_or_duplicate_schema_keys_refuse(self):
        base={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://qualityrag.local/schemas/source/v1.0','$ref':'#/$defs/Value','$defs':{'Value':{'type':'string'}}}
        with tempfile.TemporaryDirectory() as directory,patch.object(contracts,'CATALOG',Path(directory)):
            path=Path(directory)/'source.json';path.write_text(json.dumps(base));contracts.validate('source','fixture')
            for identity in ('https://qualityrag.local/schemas/source/v2.0','https://elsewhere.invalid/source/v1.0','https://qualityrag.local/schemas/source/v1'):
                path.write_text(json.dumps({**base,'$id':identity}))
                with self.assertRaises(ValueError):contracts.load_schema('source')
            path.write_text('{"$id":"x","$id":"y"}')
            with self.assertRaises(ValueError):contracts.load_schema('source')

    def test_schema_size_limit_and_unknown_names_refuse(self):
        for name in ('../../outside',None,False):
            with self.assertRaises(ValueError):contracts.load_schema(name)
        with tempfile.TemporaryDirectory() as directory,patch.object(contracts,'CATALOG',Path(directory)):
            (Path(directory)/'source.json').write_bytes(b' '*262145)
            with self.assertRaises(ValueError):contracts.load_schema('source')


class SchemaAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.InventoryCompletionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.item=self.fixture.item;self.inventory=self.fixture.inventory
        self.item['story_id']='US-002'
        source=Path(contracts.__file__).resolve().parents[2]
        paths=['tools/activation_runtime/'+directory+'/'+name+'.json' for directory in ('schemas','fixtures') for name in contracts.NAMES]
        paths+=['tools/activation_runtime/'+name for name in ('contracts.py','schema_completion.py','inventory_completion.py')]
        modules=[];tree=self.fixture.responses['/git/trees/'+'1'*40+'?recursive=1']['tree']
        for path in sorted(paths):
            target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/path,target);raw=target.read_bytes()
            modules.append({'path':path,'sha256':sha256(raw).hexdigest()})
            tree.append({'path':path,'type':'blob','sha':sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
        self.item['modules']=modules
        proof=self.item['completion_evidence'];proof.update(kind=KIND,module_inventory_sha256=fingerprint(modules),catalog_report_sha256=fingerprint(contracts.catalog_report()))
        self.fixture.responses['/actions/runs/123/jobs?per_page=100']['jobs'][0]['steps'].append({'name':STEP,'conclusion':'success'})

    def check(self):return verify(self.item,self.inventory,self.root,_fetch=lambda path:deepcopy(self.fixture.responses[path]))

    def test_catalog_acceptance_remains_software_only(self):
        row=self.check();self.assertEqual(row['scope'],'VERSIONED_SCHEMA_SOFTWARE_ONLY');self.assertEqual(row['schema_count'],10)
        self.assertEqual(row['independent_domain_validation'],'NOT_ESTABLISHED')

    def test_catalog_receipt_cannot_accept_another_story(self):
        self.item['story_id']='US-009'
        with self.assertRaises(ValueError):self.check()

    def test_report_tampering_or_missing_pinned_schema_refuses(self):
        proof=self.item['completion_evidence'];digest=proof['catalog_report_sha256'];proof['catalog_report_sha256']='0'*64
        with self.assertRaises(ValueError):self.check()
        proof['catalog_report_sha256']=digest;self.item['modules'].pop()
        with self.assertRaises(ValueError):self.check()

    def test_missing_catalog_ci_step_refuses(self):
        self.fixture.responses['/actions/runs/123/jobs?per_page=100']['jobs'][0]['steps'].pop()
        with self.assertRaises(ValueError):self.check()

    def test_successful_ci_for_another_commit_cannot_accept_catalog(self):
        self.fixture.responses['/actions/runs/123']['head_sha']='2'*40
        with self.assertRaises(ValueError):self.check()

    def test_catalog_report_checks_target_source_not_an_unrelated_local_catalog(self):
        path=self.root/'tools/activation_runtime/schemas/source.json';path.write_text('{"type":"object"}')
        with self.assertRaises(ValueError):self.check()
