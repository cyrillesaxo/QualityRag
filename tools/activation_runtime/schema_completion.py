"""US-002 acceptance checks the catalog itself plus actual immutable CI evidence."""
from pathlib import Path
from .common import fingerprint
from .contracts import catalog_report,NAMES
from .inventory_completion import verify_ci_sources,REQUIRED_STEPS

KIND='GITHUB_VERIFIED_SCHEMA_CATALOG/v1'
STEP='Run python -m tools.activation_runtime.cli catalog > /tmp/schema-catalog.json'


def verify(item,inventory,root,*,_fetch=None):
    if item.get('story_id')!='US-002':raise ValueError('Catalog acceptance applies only to US-002')
    report=catalog_report(Path(root)/"tools/activation_runtime")
    if item.get('completion_evidence',{}).get('catalog_report_sha256')!=fingerprint(report):raise ValueError('Catalog evidence changed')
    required={'tools/activation_runtime/contracts.py','tools/activation_runtime/schema_completion.py','tools/activation_runtime/inventory_completion.py'}
    required|={'tools/activation_runtime/'+directory+'/'+name+'.json' for directory in ('schemas','fixtures') for name in NAMES}
    if not required.issubset({m['path'] for m in item['modules']}):raise ValueError('Incomplete catalog source inventory')
    checked=verify_ci_sources(item,root,KIND,_fetch=_fetch,extra_keys={'catalog_report_sha256'},required_steps=REQUIRED_STEPS|{STEP})
    return {'story_id':'US-002','scope':'VERSIONED_SCHEMA_SOFTWARE_ONLY',**checked,'schema_count':report['schema_count'],
            'catalog_report_sha256':fingerprint(report),'independent_domain_validation':'NOT_ESTABLISHED'}
