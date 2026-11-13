"""Observe pinned GitHub Actions metadata; never start workflows or run seller code."""
import os
from fastapi import HTTPException
from .github_source import get_api, SHA_RE, REPO_RE


def observe_ci(repository: str, sha: str, token: str | None = None) -> dict:
    default = {'status':'NOT_AVAILABLE','origin':'GITHUB_ACTIONS',
               'runs_checked':0,'observed_sha_match':False}
    if os.getenv('GITHUB_CI_LOOKUP_DISABLED')=='1' or not REPO_RE.fullmatch(repository) or not SHA_RE.fullmatch(sha):
        return default
    try:
        result=get_api('/repos/'+repository+'/actions/runs', token,
                       params={'head_sha':sha, 'per_page':20})
        runs=[r for r in result.get('workflow_runs', []) if isinstance(r,dict) and r.get('head_sha')==sha][:20]
        if not runs:return default
        concluded=[r for r in runs if r.get('status')=='completed']
        if any(r.get('conclusion') in ('failure','timed_out','action_required') for r in concluded): status='OBSERVED_FAILURE'
        elif len(concluded)<len(runs):status='OBSERVED_IN_PROGRESS'
        elif concluded and all(r.get('conclusion')=='success' for r in concluded):status='OBSERVED_SUCCESS'
        else:status='NOT_AVAILABLE'
        return {'status':status,'origin':'GITHUB_ACTIONS', 'runs_checked':len(runs), 'observed_sha_match':True}
    except (HTTPException,ValueError,TypeError,KeyError,AttributeError):
        return {**default, 'status':'QUERY_FAILED'}
