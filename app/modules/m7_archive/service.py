from app.modules.m7_archive.export_out import checksum

def execute(state):
    process=state.get('process')
    process_ready=bool(process) and bool(process.get('balanced',False))
    ready=bool(state.get('reconcile',{}).get('balanced',False)) and process_ready
    count=len(state.get('calculations',[]))+len(state['quarantine'])
    if process:count+=len(process['dispositions'])+len(process['intake'].get('process_quarantine',[]))
    state['archive']={'sha256':checksum(state),'evidence_count':count,'ready':ready,'process_ready':process_ready}
    state['archive']['sha256']=checksum(state)
    return state
