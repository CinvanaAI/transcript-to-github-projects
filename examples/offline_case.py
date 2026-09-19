"""Actual analysis coordinator, with synthetic provider/config/evidence boundaries."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from app import pipeline
from app.config import AppConfig
from app.providers.base import ModelCapability
from app.schema import validate_project_data
from app.translator import build_transcript_extraction_messages


def demonstrate(root):
    transcript='User: Make a review queue. Require approval before publishing any item.'
    source=root/'source.txt';source.write_text(transcript,encoding='utf-8')
    plan={'project_title':'Workshop Review Queue','project_description':'Review proposed work before publication.','source_summary':'Synthetic planning request.','items':[{'type':'Task','title':'Add a review gate','body':'Require a person to approve each draft.','priority':'High','confidence':'High','phase':'V1','needs_review':True}]}
    class FixtureProvider:
        def get_model_capability(self,_):return ModelCapability(False,True,False,'Fixture only')
        def analyze_transcript(self,text,model,config):
            assert text==transcript
            return json.dumps(plan)
    config=AppConfig('','synthetic-model','','example-lab','http://localhost:11434','https://ollama.com','')
    observed=[]
    with patch.object(pipeline,'load_config',lambda **_:config),patch.object(pipeline,'get_provider_adapter',lambda _:FixtureProvider()),patch.object(pipeline,'_record_analysis_compatibility',lambda **record:observed.append(record)):
        result=pipeline.analyze_transcript(source,model_override='synthetic-model',output_path=root/'response.json')
    validated=validate_project_data(json.loads(result.raw_response_text))
    return {'mode':'Actual coordinator; synthetic provider response','source':transcript,'request_roles':[m['role'] for m in build_transcript_extraction_messages(transcript)],'captured_response':json.loads((root/'response.json').read_text()),'reviewed_project_title':validated['project_title'],'compatibility_status':observed[0]['classification_status'],'published':False,'network_calls':0}


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='transcript-case-') as scratch:print(json.dumps(demonstrate(Path(scratch)),indent=2))
