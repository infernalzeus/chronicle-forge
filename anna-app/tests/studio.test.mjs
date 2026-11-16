import test from 'node:test';
import assert from 'node:assert/strict';
import {imageRect} from '../bundle/framing.mjs';
import {planScenes} from '../bundle/video-plan.mjs';
import {generateMedia} from '../bundle/video.mjs';
for(const [label,w,h] of [['portrait',600,1400],['square',1024,1024],['panorama',2400,600]])test(`${label} whole-image framing preserves every edge`,()=>{
 const r=imageRect(w,h,1280,720);assert.ok(r.x>=0&&r.y>=0);assert.ok(r.x+r.width<=1280.00001&&r.y+r.height<=720.00001);assert.ok(Math.abs(r.width/r.height-w/h)<.00001);
});
test('cropped fill mode is explicit and covers the output',()=>{const r=imageRect(600,1400,1280,720,'cover');assert.equal(r.width,1280);assert.ok(r.y<0);});
test('requested image count works even with a single sentence',()=>{const text='One long sentence has enough words to divide across four scene images.';const scenes=planScenes(text,4);assert.equal(scenes.length,4);assert.equal(scenes.map(s=>s.text).join(' '),text);});
test('short narration cannot produce empty scene cards',()=>assert.equal(planScenes('The Moon.',24).length,2));
test('invalid scene counts fail before paid calls',()=>{for(const count of [0,25,2.5,NaN])assert.throws(()=>planScenes('A factual narration.',count),/1–24/);});
test('the first illustration is published to the UI before speech finishes',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(new Blob(['image'],{type:'image/png'})));
 let resolveSpeech;const speech=new Promise(r=>resolveSpeech=r);const scene={text:'A factual scene.'};const updates=[];
 const anna={image:{generateAsync:async()=>({jobId:'ijob_live'}),getJob:async()=>({state:'succeeded',result:{images:[{url:'https://example.com/image.png'}]}})},audio:{speak:()=>speech}};
 const run=generateMedia(anna,{scenes:[scene]},{imageModel:'test',ttsModel:'test'},()=>{},undefined,state=>updates.push({...state,imageReady:Boolean(scene.imageBlob),voiceReady:Boolean(scene.audioBlob)}));
 for(let i=0;i<10&&!scene.imageBlob;i++)await new Promise(r=>setTimeout(r,0));
 assert.ok(updates.some(x=>x.completed===1&&x.imageReady&&!x.voiceReady));resolveSpeech({audioBase64:'YWJj'});await run;assert.equal(updates.at(-1).completed,2);
});

test('preview quality is forwarded to Anna without generating extra images',async t=>{
 t.mock.method(globalThis,'fetch',async()=>new Response(new Blob(['image'],{type:'image/png'})));
 let calls=0,quality;const anna={image:{generateAsync:async args=>{calls++;quality=args.quality;return {jobId:'ijob_quality'};},getJob:async()=>({state:'succeeded',result:{images:[{url:'https://example.com/image.png'}]}})}};
 const project={scenes:[{text:'A fact.',audioBlob:new Blob(['audio'])}]};await generateMedia(anna,project,{imageModel:'test',imageQuality:'low'},()=>{});assert.equal(quality,'low');assert.equal(calls,1);
});
