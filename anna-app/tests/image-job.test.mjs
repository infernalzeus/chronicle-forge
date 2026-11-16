import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneImage} from '../bundle/image-job.mjs';
import {saveProject,loadProject} from '../bundle/project.mjs';
test('slow image jobs show progress and return authoritative output',async()=>{
 let polls=0,starts=0;const messages=[];const scene={};
 const anna={image:{generateAsync:async args=>{starts++;assert.ok(args.idempotencyKey);return {jobId:'ijob_test'};},getJob:async()=>++polls===1?{state:'queued',progress:{queuePosition:2}}:{state:'succeeded',result:{images:[{url:'https://example.com/image.png'}]}}}};
 assert.equal(await sceneImage(anna,scene,{},x=>messages.push(x),undefined,{pollMs:0}),'https://example.com/image.png');assert.equal(starts,1);assert.match(messages[0],/queue position 2/);
});
test('retry after polling failure retrieves the paid job without another submission',async()=>{
 const scene={};let starts=0;let fail=true;const anna={image:{generateAsync:async()=>{starts++;return {jobId:'ijob_paid'};},getJob:async()=>{if(fail)throw new Error('network');return {state:'succeeded',result:{images:[{url:'https://example.com/paid.png'}]}};}}};
 await assert.rejects(sceneImage(anna,scene,{},()=>{}),/network/);fail=false;await sceneImage(anna,scene,{},()=>{});assert.equal(starts,1);
});
test('failed provider jobs cannot be mistaken for completed media',async()=>{
 const scene={imageJobId:'ijob_failed',imageRequestKey:'key'};
 await assert.rejects(sceneImage({image:{getJob:async()=>({state:'failed',error:{message:'Provider unavailable'}})}},scene,{},()=>{}),/Provider unavailable/);assert.equal(scene.imageJobId,undefined);
});
test('saved projects preserve in-flight image jobs for recovery',async()=>{
 const saved=await saveProject({topic:'Moon'},{scenes:[{text:'Moon.',imageJobId:'ijob_paid',imageRequestKey:'key'}]},'Moon.',{});
 assert.equal(loadProject(saved).project.scenes[0].imageJobId,'ijob_paid');
});
