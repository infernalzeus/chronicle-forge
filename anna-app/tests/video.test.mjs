import test from 'node:test';
import assert from 'node:assert/strict';
import {planScenes,timelineFromDurations,srtFromScenes} from '../bundle/video-plan.mjs';
import {generateMedia} from '../bundle/video.mjs';

test('scene planning preserves the narration and stays within speech limits',()=>{
  const text=Array.from({length:30},(_,i)=>`This is documented sentence ${i+1}.`).join(' ');
  const scenes=planScenes(text,3);
  assert.equal(scenes.map(x=>x.text).join(' '),text);
  assert.ok(scenes.every(x=>x.text.length<=850));
});
test('oversize unpunctuated narration is safely split',()=>{
  const text='word '.repeat(500).trim();const scenes=planScenes(text,3);
  assert.equal(scenes.map(x=>x.text).join(' '),text);assert.ok(scenes.every(x=>x.text.length<=850));
});
test('empty narration cannot incur media costs',()=>assert.throws(()=>planScenes(' '),/Narration/));
test('timeline uses actual audio durations without gaps or overlap',()=>{
  assert.deepEqual(timelineFromDurations([2,3.5,1]),[{start:0,end:2,duration:2},{start:2,end:5.5,duration:3.5},{start:5.5,end:6.5,duration:1}]);
});
test('invalid audio duration cannot create a video',()=>assert.throws(()=>timelineFromDurations([2,0]),/valid speech/));
test('subtitles end exactly at final audio boundary',()=>{
  const srt=srtFromScenes([{text:'First sentence.'},{text:'Second sentence.'}],timelineFromDurations([2,3]));
  assert.match(srt,/00:00:02,000 --> 00:00:05,000/);
});
test('cancelled media generation never calls any model',async()=>{
  const controller=new AbortController();controller.abort();
  await assert.rejects(generateMedia({}, {scenes:[{text:'A fact.'}]},{},()=>{},controller.signal),/Stopped/);
});
test('completed media retries do not regenerate paid assets',async()=>{
  const project={scenes:[{text:'A fact.',imageBlob:new Blob(['image']),audioBlob:new Blob(['audio'])}]};
  assert.equal(await generateMedia({},project,{},()=>{}),project);
});
test('hosted speech uses the selected Anna model and no local server',async()=>{
  const calls=[];const anna={audio:{speak:async args=>{calls.push(args);return {audioBase64:'YWJj',mimeType:'audio/mpeg',model:'Anna speech'};}}};
  const project={scenes:[{text:'A fact.',imageBlob:new Blob(['image'])}]};
  await generateMedia(anna,project,{ttsModel:'Anna speech',voice:'Voice'},()=>{});
  assert.deepEqual(calls,[{text:'A fact.',model:'Anna speech',voice:'Voice',delivery:'inline',format:'mp3'}]);
  assert.equal(project.scenes[0].audioBlob.size,3);
});
test('speech failure preserves the generated image for retry',async()=>{
  const project={scenes:[{text:'A fact.',imageBlob:new Blob(['image'])}]};
  await assert.rejects(generateMedia({audio:{speak:async()=>{throw new Error('quota');}}},project,{},()=>{}),/quota/);
  assert.equal(project.scenes[0].imageBlob.size,5);
});
