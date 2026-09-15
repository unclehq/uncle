"""Opt-in reuse for explicitly declared deterministic, side-effect-free checks."""
import hashlib,json,os,shlex,shutil
from pathlib import Path
from verification_manifest import manifest
from evidence_index import save


def key(command):
    state=Path('.uncle/workflow')
    policy=state/'check-reuse.json'
    try:
        rule=json.loads(policy.read_text()).get(command,{})
        if rule.get('deterministic_read_only') is not True or rule.get('always_run') is not False:
            return None
        scopes=rule['input_scopes']
        if not isinstance(scopes,str) or not Path(scopes).is_file():return None
        # Rules must list source, tests, fixtures, lockfiles and relevant config.
        inputs=manifest(scopes)
        if not inputs:return None
        env = {k:v for k,v in os.environ.items() if k not in ('UNCLE_TIMING_STAGE', 'UNCLE_STATUS_STAGE', 'UNCLE_STATUS_FILE', 'UNCLE_STEERING', 'UNCLE_SUPERVISION_HOST', 'SHLVL', '_')}
        environment=hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest()
        tokens=shlex.split(command)
        if not tokens or any(token in command for token in ('&&','||',';','|','$','`')):return None
        executable=shutil.which(tokens[0])
        shell=shutil.which('bash')
        if not executable or not shell:return None
        runtimes=[]
        for file in (executable,shell):
            runtimes.append([str(Path(file).resolve()),hashlib.sha256(Path(file).read_bytes()).hexdigest()])
        data=[command,rule,inputs,environment,runtimes,os.environ.get('UNCLE_TIMING_DIR','')]
        digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        return state/'check-reuse-results'/f'{digest}.json'
    except (OSError,ValueError,KeyError,TypeError):return None


def restore(path,output):
    if path is None:return False
    try:
        row=json.loads(path.read_text())
        if row.get('status')!=0:return False
        output.write(('REUSED successful deterministic check; original evidence follows.\n'+row['output']).encode())
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def record(path,log):
    if path is not None:
        try:save(path,{'status':0,'output':Path(log).read_text(errors='replace')})
        except OSError:pass
