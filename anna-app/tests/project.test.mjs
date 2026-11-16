import test from 'node:test';
import assert from 'node:assert/strict';
import {saveProject,loadProject} from '../bundle/project.mjs';
test('resumable project retains already-paid image and speech bytes',async()=>{
  const draft={topic:'Moon',sources:[],audit:'Review required'},project={scenes:[{text:'The Moon orbits Earth.',imageBlob:new Blob(['image'],{type:'image/png'}),audioBlob:new Blob(['speech'],{type:'audio/mpeg'})}]};
  const loaded=loadProject(await saveProject(draft,project,'The Moon orbits Earth.',{style:'refined'}));
  assert.equal(await loaded.project.scenes[0].imageBlob.text(),'image');assert.equal(await loaded.project.scenes[0].audioBlob.text(),'speech');
});
test('foreign files are rejected without executing or fetching content',()=>assert.throws(()=>loadProject('{"format":"other"}'),/Invalid/));
test('project with executable media type is rejected',()=>{
  const data={format:'chronicle-forge-video-project-v1',draft:{topic:'Moon'},narration:'The Moon.',scenes:[{text:'The Moon.',image:{type:'text/html',data:'PGgxPg=='}}]};
  assert.throws(()=>loadProject(JSON.stringify(data)),/Invalid project media/);
});
