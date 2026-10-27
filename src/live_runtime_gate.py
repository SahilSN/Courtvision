"""Fail closed on stale imported Live validators; never reload running modules."""
import ast
import importlib
from pathlib import Path
from types import CodeType

# Validate function code AND literal policy data. A matching file on disk alone
# is not evidence that an already-imported function is current.
MODULES = ('season_config','live_artifacts','probe_live_access','live_game_date','live_rollout','daily_live_policy','live_operations','official_live_rosters','reviewed_live_players','live_diagnostics','source_score_ledger','cloud_espn_adapter','cloud_espn_box',
           'daily_live_context','live_snapshot_cache','cloud_live_bundle',
           'cloud_live_analysis','live_refresh','live_analysis','feature_engineering')
LITERALS = {'season_config':('CURRENT_SEASON','CURRENT_SEASON_TYPE'),
            'live_game_date':('OVERNIGHT_END_HOUR',),
            'probe_live_access':('BASE','MAX_BYTES'),
            'live_rollout':('MAX_LIVE_GAMES',),
            'cloud_live_bundle':('SCORE_RETRY_ATTEMPTS','SCORE_RETRY_DELAY','SCORE_RETRY_BUDGET'),
            'reviewed_live_players':('REVIEWED',),'cloud_espn_box':('COUNTS','SHOTS')}


def module_matches(module, path, literals=()):
    source=Path(path).read_text()
    tree=ast.parse(source)
    compiled=compile(source,str(path),'exec',dont_inherit=True)
    expected={c.co_name:c for c in compiled.co_consts if isinstance(c,CodeType)}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            value=getattr(module,node.name,None)
            if isinstance(node,ast.FunctionDef):
                # lru_cache decorators retain the underlying Python function.
                value=getattr(value,'__wrapped__',value)
                if getattr(value,'__code__',None)!=expected[node.name]:return False
            else:
                methods={c.co_name:c for c in expected[node.name].co_consts if isinstance(c,CodeType)}
                for method in node.body:
                    if isinstance(method,ast.FunctionDef):
                        value_method=getattr(value,method.name,None)
                        if getattr(value_method,'__code__',None)!=methods[method.name]:return False
    for name in literals:
        assignments=[n.value for n in tree.body if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
        if len(assignments)!=1 or getattr(module,name,None)!=ast.literal_eval(assignments[0]):return False
    return True


def runtime_ready(root):
    try:
        modules={name:importlib.import_module(name) for name in MODULES}
        for name,module in modules.items():
            if not module_matches(module,Path(root)/'src'/f'{name}.py',LITERALS.get(name,())):
                return False
        # Check every direct import between these modules, including classes
        # and configuration constants, rather than maintaining a partial list.
        for consumer,module in modules.items():
            tree=ast.parse((Path(root)/'src'/f'{consumer}.py').read_text())
            for node in tree.body:
                if isinstance(node,ast.ImportFrom) and node.module in modules:
                    for alias in node.names:
                        if getattr(module,alias.asname or alias.name,None) is not getattr(modules[node.module],alias.name,None):return False
        return True
    except Exception:
        # Missing/partially deployed source or failed imports are not approval.
        return False
