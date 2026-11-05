"""Versioned local shape catalog; shape validation never grants semantic admission."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
from .common import canonical,strict_json,fingerprint

CATALOG=Path(__file__).with_name('schemas')
NAMES=frozenset({'grammar','source','payload','transform','packspec','verdict','receipt','operator-ast','reviewed-activation','observation-graph'})


def load_schema(name,*,catalog=None):
    if not isinstance(name,str) or name not in NAMES:raise ValueError('Unknown schema')
    with ((CATALOG if catalog is None else Path(catalog))/(name+'.json')).open('rb') as stream:raw=stream.read(262145)
    schema=strict_json(raw,max_bytes=262144)
    prefix='https://qualityrag.local/schemas/'+name+'/v1.'
    if (not isinstance(schema,dict) or schema.get('$schema')!='https://json-schema.org/draft/2020-12/schema'
        or not isinstance(schema.get('$id'),str) or not re.fullmatch(re.escape(prefix)+r'(0|[1-9][0-9]*)',schema['$id'])):
        raise ValueError('Pinned catalog namespace, dialect and major/minor version required')
    pending=[schema]
    while pending:
        node=pending.pop()
        if isinstance(node,dict):
            for keyword in ('$ref','$dynamicRef'):
                if keyword in node and (not isinstance(node[keyword],str) or not node[keyword].startswith('#')):
                    raise ValueError('Remote schema reference prohibited')
            if node is not schema and '$id' in node:raise ValueError('Nested schema base changes prohibited')
            pending.extend(node.values())
        elif isinstance(node,list):pending.extend(node)
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(schema)
    return schema


def validate(name,value,*,_catalog=None):
    from jsonschema import Draft202012Validator
    canonical(value)
    schema=load_schema(name,catalog=_catalog)
    Draft202012Validator(schema).validate(value)
    if name in {'packspec','observation-graph'}:
        key='node_id' if name=='packspec' else 'id';ids=[node[key] for node in value['nodes']]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate node ID')
    return value


def catalog_report(root=None):
    """Observed catalog/software checks, not domain acceptance or signer authority."""
    from jsonschema import ValidationError
    fixtures=Path(__file__).with_name('fixtures') if root is None else Path(root)/'fixtures'
    catalog=CATALOG if root is None else Path(root)/'schemas'
    rows=[];values={};ids=set()
    for name in sorted(NAMES):
        schema=load_schema(name,catalog=catalog)
        if schema['$id'] in ids:raise ValueError('Duplicate schema identifier')
        ids.add(schema['$id'])
        with (fixtures/(name+'.json')).open('rb') as stream:raw=stream.read(524289)
        value=strict_json(raw);validate(name,value,_catalog=catalog);values[name]=value
        encoded=canonical(value)
        if canonical(strict_json(encoded))!=encoded:raise ValueError('Nondeterministic canonical round-trip')
        rows.append({'name':name,'schema_id':schema['$id'],'schema_sha256':fingerprint(schema),
            'fixture_sha256':sha256(raw).hexdigest(),'canonical_fixture_sha256':sha256(encoded).hexdigest()})
    probes={}
    bad=deepcopy(values['packspec']);bad['nodes'].append(deepcopy(bad['nodes'][0]));probes['duplicate_node_id']=('packspec',bad)
    bad=deepcopy(values['grammar']);bad['operators']=['EDGE','EXEC'];probes['unknown_operator']=('grammar',bad)
    probes['invalid_type']=('source',{'field':[]});probes['oversize_payload']=('payload',{'field':'x'*524288})
    bad=deepcopy(values['transform']);bad['schema']='qualityrag.finite-activation/v999';probes['incompatible_major']=('transform',bad)
    rejected={}
    for name,(kind,value) in probes.items():
        errors=[]
        for _ in range(2):
            try:validate(kind,value,_catalog=catalog)
            except (ValueError,ValidationError) as exc:errors.append(type(exc).__name__)
            else:raise ValueError('Catalog accepted required rejection witness: '+name)
        if errors[0]!=errors[1]:raise ValueError('Inconsistent catalog rejection')
        rejected[name]={'result':'REJECTED','error_type':errors[0]}
    return {'schema':'qualityrag.catalog-report/v1','schemas':rows,'rejection_witnesses':rejected,
        'schema_count':len(rows),'canonical_round_trip':'PASSED','scope':'VERSIONED_SCHEMA_SOFTWARE_ONLY',
        'semantic_admission':'INCONCLUSIVE','can_generate':False}
