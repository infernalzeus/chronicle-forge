import {timingHistory,formatTime,quotaFailure} from './timing.mjs';
import {createDiagnostics} from './diagnostics.mjs';
import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";
import {researchTopic, draftNarration} from './workflow.mjs';
import {planScenes} from './video-plan.mjs';
import {checkEncoding, generateMedia, decodeProject, renderMp4, exportSmokeTest} from './video.mjs';
import {saveProject,loadProject,mediaIdentity} from './project.mjs';
import {imageRect} from './framing.mjs';
const el=id=>document.getElementById(id);
let anna, research, draft, project, finished, busyNow=false, controller;
let imageModels=[],ttsModels=[];
const objectUrls=[];const diagnostics=createDiagnostics();
let latestStatus='',startedAt=0,activeAsset=null,operationFailed=false;let timingStorage;try{timingStorage=localStorage;}catch{}const timings=timingHistory(timingStorage);
function message(text){
  latestStatus=text;el('status').textContent=text;el('activity-message').textContent=text;
  const log=el('activity-log'),last=log.lastElementChild;
  if(!last||last.textContent!==text){const item=document.createElement('li');item.textContent=text;log.append(item);while(log.children.length>40)log.firstElementChild.remove();}
}
function updateAssetTiming(){
  if(!activeAsset)return;const age=Date.now()-activeAsset.startedAt,average=timings.average(activeAsset.kind,activeAsset.model,activeAsset.quality);
  el('asset-title').textContent=`${activeAsset.kind==='image'?'Illustration':'Voice'} · scene ${activeAsset.index}`;
  el('asset-elapsed').textContent=`${formatTime(age)} elapsed for this asset`;
  el('asset-average').textContent=average?`Recent average: ${formatTime(average.ms)} · ${average.count} completed ${average.count===1?'sample':'samples'}. ${age>average.ms?'Taking longer than the recent average.':'Queue and provider speed can vary.'}`:'No measured average for this model/quality yet. The first completion will establish one.';
  el('asset-wait').hidden=!busyNow;
}
function progressState({stage,completed,total,asset}){
  if(asset){if(asset.complete){if(asset.sampleEligible)timings.record(asset.kind,asset.model,asset.quality,asset.elapsedMs);activeAsset=null;el('asset-title').textContent=`${asset.kind==='image'?'Illustration':'Voice'} ready · scene ${asset.index}`;el('asset-elapsed').textContent=`Completed in ${formatTime(asset.elapsedMs)}`;el('asset-average').textContent='Your completed asset is retained for retries.';el('asset-wait').hidden=true;}else{activeAsset=asset;updateAssetTiming();}}

  diagnostics.record(stage,'progress',{completed,total});
  const value=total?Math.max(0,Math.min(100,completed/total*100)):0;
  el('work-progress').hidden=false;el('work-progress').value=value;
  el('progress-label').textContent=stage==='media'?'Completed media assets':'Video encoding';
  el('progress-value').textContent=stage==='media'?`${Math.round(value)}% · ${completed}/${total} assets ready. Overall completed work — not progress inside the current image.`:`${Math.round(value)}% · ${Math.floor(completed)}/${total} scenes encoded`;
}
function settings(){return {imageModel:el('image-model').value,ttsModel:el('tts-model').value,voice:el('voice').value,style:el('style').value,sceneCount:Number(el('scene-count').value),imageQuality:el('image-quality').value};}
function currentProject(){return project?.identity===mediaIdentity(el('narration').value.trim(),settings())?project:null;}
function plannedScenes(){try{return planScenes(el('narration').value,Number(el('scene-count').value));}catch{return [];}}
function updatePlan(){
  const seconds=Number(el('duration').value),count=Number(el('scene-count').value),words=el('narration').value.trim().split(/\s+/).filter(Boolean).length;
  el('plan-summary').textContent=`Plan: about ${seconds||0}s · ${count||0} scene images · ${el('style').value==='stickman'?'stick figures':'detailed illustrations'}. Image and voice generation happens only in step 3.`;
  el('narration-summary').textContent=words?`${words} words · roughly ${Math.round(words/2)} seconds at a normal speaking pace. Actual timing comes from the voice audio.`:'Review and edit the script before purchasing media.';
  const scenes=plannedScenes();el('media-estimate').textContent=scenes.length?`${scenes.length} planned scenes: up to ${scenes.length} image calls and ${scenes.length} voice calls. ${project?'Completed assets are kept; changing the script, scene count, style or models starts a new media plan.':'Review the scene text below before generating.'}`:'Your scene plan appears here after a script is ready.';
  el('motion').disabled=busyNow||el('fit').value!=='cover';
  if(el('fit').value!=='cover')el('motion').checked=false;
}
function clearOutput(){finished=null;el('preview').pause();el('preview').removeAttribute('src');el('preview').hidden=true;el('preview-label').textContent='';}
setInterval(()=>{if(busyNow){el('elapsed').textContent=`${formatTime(Date.now()-startedAt)} total elapsed`;updateAssetTiming();}},1000);
function download(blob,name){const url=URL.createObjectURL(blob);objectUrls.push(url);const a=document.createElement('a');a.href=url;a.download=name;a.click();}
function controls(){
  el('research').disabled=busyNow||!anna;el('draft').disabled=busyNow||!research;
  el('generate').disabled=busyNow||!draft||!el('reviewed').checked||!el('image-model').value||!el('tts-model').value;
  el('render').disabled=busyNow||!(currentProject()?.scenes.length&&currentProject().scenes.every(s=>s.imageBlob&&s.audioBlob));
  el('catalog').disabled=busyNow||!anna;el('smoke').disabled=busyNow;
  el('stop').disabled=!busyNow;el('activity-stop').hidden=!busyNow;el('export').disabled=busyNow||!draft;
  el('download').disabled=busyNow||!finished;el('subtitles').disabled=busyNow||!finished;
  el('thumbnail').disabled=busyNow||!currentProject()?.scenes[0]?.imageBlob;
  el('save-project').disabled=busyNow||!draft;el('open-project').disabled=busyNow;
  el('narration').disabled=busyNow;el('reviewed').disabled=busyNow;
  for(const id of ['duration','scene-count','image-quality','topic','image-model','tts-model','voice','style','resolution','captions','fit','motion'])el(id).disabled=busyNow;
  document.querySelectorAll('[name=visual-style]').forEach(x=>x.disabled=busyNow);updatePlan();
}
async function busy(task,stage='operation'){if(busyNow)return;busyNow=true;operationFailed=false;el('activity').dataset.state='working';startedAt=Date.now();diagnostics.record(stage,'start');el('elapsed').textContent='Starting…';el('activity').setAttribute('aria-busy','true');el('work-progress').hidden=false;el('work-progress').removeAttribute('value');el('progress-value').textContent='Waiting for Anna; no completed work yet.';el('monitor-title').textContent='Working';controller=new AbortController();controls();
  try{await task(controller.signal);diagnostics.record(stage,'complete',{duration_ms:Date.now()-startedAt});}catch(e){operationFailed=true;el('activity').dataset.state='error';diagnostics.record(stage,'failed',{duration_ms:Date.now()-startedAt,error_code:quotaFailure(e)?'APP_QUOTA_EXCEEDED':e.code||'operation_failed'});message(quotaFailure(e)?'Anna quota reached. Generation paused; completed assets are safe in this window. Save your project now. Check Anna Subscription & Usage before resuming. Retrying before quota is available will fail again.':`Could not complete${e.code?` (${e.code})`:''}: ${e.message}. Completed assets are retained. Save a project backup before closing this window.`);}

  finally{busyNow=false;el('activity').setAttribute('aria-busy','false');if(!el('work-progress').hasAttribute('value')){el('work-progress').hidden=true;el('progress-value').textContent='No operation running';}el('monitor-title').textContent=operationFailed?'Paused — action needed':'Ready for the next step';el('asset-wait').hidden=true;activeAsset=null;el('elapsed').textContent=`Finished after ${Math.floor((Date.now()-startedAt)/1000)}s`;controls();}}
function showSources(){el('sources').replaceChildren();for(const source of research.sources){
  const row=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=source.id;
  row.append(input,document.createTextNode(` [${source.id}] ${source.title} — ${source.url}`));
  const details=document.createElement('details'),summary=document.createElement('summary'),p=document.createElement('p'),a=document.createElement('a');
  summary.textContent=source.truncated?'Read excerpt (page truncated)':'Read source excerpt';p.textContent=source.content;
  a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Open original source';details.append(summary,p,a);el('sources').append(row,details);
}}
function renderAssets(){
  el('assets').replaceChildren();const current=currentProject(),scenes=current?.scenes||plannedScenes();if(!current){el('latest-image').hidden=true;el('latest-image-label').textContent=project?'Settings changed. The previous assets are retained until you generate a new plan.':'Your first image will appear as soon as it is ready.';}
  scenes.forEach((scene,i)=>{
    const card=document.createElement('article'),title=document.createElement('h3'),p=document.createElement('p');title.textContent=`Scene ${i+1}`;p.textContent=scene.text;card.append(title);
    if(scene.imageBlob){const img=document.createElement('img');img.src=URL.createObjectURL(scene.imageBlob);objectUrls.push(img.src);img.alt=`AI illustration for scene ${i+1}`;card.append(img);el('latest-image').src=img.src;el('latest-image').hidden=false;el('latest-image-label').textContent=`Scene ${i+1} · completed image`;
    }else{const placeholder=document.createElement('div');placeholder.className='scene-placeholder';placeholder.textContent=scene.imageJobId?'Image queued / rendering on Anna':'Illustration not generated';card.append(placeholder);}
    card.append(p);const state=document.createElement('p');state.className='scene-state';state.textContent=`Image: ${scene.imageBlob?'ready':scene.imageJobId?'in progress':'pending'} · Voice: ${scene.audioBlob?'ready':'pending'}`;card.append(state);
    if(scene.audioBlob){const audio=document.createElement('audio');audio.controls=true;audio.src=URL.createObjectURL(scene.audioBlob);objectUrls.push(audio.src);card.append(audio);}el('assets').append(card);
  });updatePlan();
}
function populate(select,models){select.replaceChildren();for(const model of models){const option=document.createElement('option');option.value=model.modelName;option.textContent=model.displayName||model.modelName;select.append(option);}
  const preferred=models.find(m=>m.isUserPreferred);if(preferred)select.value=preferred.modelName;}
function voices(){const model=ttsModels.find(x=>x.modelName===el('tts-model').value);populate(el('voice'),[]);
  const list=model?.capabilities?.voices||model?.voices||[];const def=document.createElement('option');def.value='';def.textContent='Model default voice';el('voice').append(def);
  for(const voice of list){const option=document.createElement('option');option.value=typeof voice==='string'?voice:voice.id;option.textContent=typeof voice==='string'?voice:(voice.name||voice.displayName||voice.id);el('voice').append(option);}}
async function catalog(){message('Checking your available Anna image and speech models…');
  const images=await anna.llm.catalog({serviceType:'image_gen'}),speech=await anna.llm.catalog({serviceType:'tts'});
  const available=images.quota?.remainingCU;el('quota-notice').textContent=Number.isFinite(available)?`Anna reports ${available} CU available. Different image and voice models cost different amounts; this does not guarantee the whole plan fits your quota.`:'Anna charges each media call separately. Start with one preview-quality scene to check your quota.';
  imageModels=images.models||[];ttsModels=speech.models||[];populate(el('image-model'),imageModels);populate(el('tts-model'),ttsModels);voices();
  message(imageModels.length&&ttsModels.length?'Anna models loaded. Generation uses Anna quota. No local AI models are called.':'Anna has not granted image or speech access yet. Enable those permissions for Chronicle Forge in Installed Apps, then click Load Anna models.');}
el('research').addEventListener('click',()=>busy(async()=>{clearOutput();research=null;draft=null;project=null;el('reviewed').checked=false;el('narration').value='';el('result').textContent='';el('sources').replaceChildren();renderAssets();
  message('Searching and reading source pages…');research=await researchTopic(anna,el('topic').value,Number(el('duration').value)<=15?1:5);showSources();message('Select relevant sources below, then draft the narration.');},'research'));
el('draft').addEventListener('click',()=>busy(async()=>{clearOutput();draft=null;project=null;el('reviewed').checked=false;renderAssets();
  const chosen=[...el('sources').querySelectorAll('input:checked')].map(x=>x.value);message('Drafting narration and comparing its claims with your selected evidence…');
  draft=await draftNarration(anna,research.topic,Number(el('duration').value),research.sources.filter(x=>chosen.includes(x.id)));
  el('narration').value=draft.narration;renderAssets();el('result').textContent=draft.sentences.map(x=>`${x.text} [${x.source_ids.join(', ')}]`).join('\n\n')+'\n\nMODEL AUDIT — HUMAN REVIEW REQUIRED\n'+draft.audit;
  message('Review the evidence and audit. Edit the narration below, then approve it before generating media.');},'script'));
el('catalog').addEventListener('click',()=>busy(catalog,'models'));el('tts-model').addEventListener('change',()=>{voices();renderAssets();controls();});
for(const id of ['image-model','image-quality','voice'])el(id).addEventListener('change',()=>{renderAssets();controls();});
el('reviewed').addEventListener('change',controls);
el('narration').addEventListener('input',()=>{el('reviewed').checked=false;controls();renderAssets();});
for(const id of ['duration','scene-count','fit','motion'])el(id).addEventListener('input',()=>{updatePlan();renderAssets();controls();});
document.querySelectorAll('[name=visual-style]').forEach(input=>input.addEventListener('change',()=>{el('style').value=input.value;updatePlan();renderAssets();controls();}));
el('generate').addEventListener('click',()=>busy(async signal=>{
  await checkEncoding();const quota=await anna.llm.catalog({serviceType:'image_gen'});if(Number.isFinite(quota.quota?.remainingCU)&&quota.quota.remainingCU<=0){const error=new Error('Anna reports no quota available');error.code='APP_QUOTA_EXCEEDED';throw error;}const text=el('narration').value.trim();
  const options=settings();
  const identity=mediaIdentity(text,options);
  if(!project||project.identity!==identity)project={identity,topic:draft.topic,scenes:planScenes(text,options.sceneCount)};
  clearOutput();message('Starting Anna media generation. Image jobs may take several minutes.');try{await generateMedia(anna,project,options,message,signal,state=>{progressState(state);renderAssets();});}finally{renderAssets();}
  message('Images and narration are ready. Preview them below, then export your MP4. No local AI model was used.');},'media'));
el('render').addEventListener('click',()=>busy(async signal=>{clearOutput();message('Preparing scene images and audio for export…');const decoded=await decodeProject(project);try{
  const width=Number(el('resolution').value);finished=await renderMp4(decoded,{width,height:width*9/16,captions:el('captions').checked,fit:el('fit').value,motion:el('motion').checked,title:project.topic,progress:message,onProgress:progressState,signal});
  const url=URL.createObjectURL(finished.blob);objectUrls.push(url);el('preview').src=url;el('preview').hidden=false;el('preview-label').textContent='Your generated documentary';
  message(`MP4 ready: ${finished.duration.toFixed(1)} seconds. Preview it, then download the MP4 and subtitles.`);
}finally{decoded.forEach(x=>x.image.close());}},'encode'));
el('smoke').addEventListener('click',()=>busy(async()=>{message('Testing browser MP4 encoding with a test image and tone. No AI model or Anna credits are used.');const result=await exportSmokeTest(message);const url=URL.createObjectURL(result.blob);objectUrls.push(url);el('preview').src=url;el('preview').hidden=false;el('preview-label').textContent='ENCODER TEST ONLY — this test card is not your documentary';download(result.blob,'chronicle-forge-export-test.mp4');message('Video export test passed: two-second H.264/AAC MP4 created and downloaded. No AI model used.');},'encoder_check'));
el('activity-stop').addEventListener('click',()=>el('stop').click());
el('stop').addEventListener('click',()=>{controller?.abort();message('Stopping after the current call. Image jobs are retained for resume; hosted calls may still consume quota.');});
el('download').addEventListener('click',()=>download(finished.blob,'chronicle-forge-video.mp4'));
el('subtitles').addEventListener('click',()=>download(new Blob([finished.srt],{type:'text/plain'}),'chronicle-forge-subtitles.srt'));
el('thumbnail').addEventListener('click',()=>busy(async()=>{
  const image=await createImageBitmap(project.scenes[0].imageBlob),canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;
  try{const ctx=canvas.getContext('2d'),rect=imageRect(image.width,image.height,1280,720,'contain');ctx.fillStyle='#101819';ctx.fillRect(0,0,1280,720);ctx.drawImage(image,rect.x,rect.y,rect.width,rect.height);
    ctx.fillStyle='rgba(0,0,0,.7)';ctx.fillRect(0,590,1280,130);ctx.fillStyle='white';ctx.font='bold 40px system-ui';ctx.fillText(project.topic,35,650,1210);ctx.font='18px system-ui';ctx.fillText('AI ILLUSTRATION · CHRONICLE FORGE',35,695);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('Thumbnail encoding failed');download(blob,'chronicle-forge-thumbnail.png');message('Thumbnail downloaded. No additional AI call was made.');
  }finally{image.close();}
},'thumbnail'));
el('export').addEventListener('click',()=>{const metadata={...draft,reviewed_narration:el('narration').value,human_approved:el('reviewed').checked,
  youtube:{title:draft.topic,description:`${draft.topic}\n\nAI-generated illustrations and synthesized narration.\nSources:\n${draft.sources.map(x=>`${x.title}: ${x.url}`).join('\n')}`}};download(new Blob([JSON.stringify(metadata,null,2)],{type:'application/json'}),'chronicle-forge-project.json');});
el('save-project').addEventListener('click',()=>busy(async()=>{
  const options=settings();
  const saved=await saveProject(draft,currentProject(),el('narration').value,{...options,fit:el('fit').value,motion:el('motion').checked,resolution:el('resolution').value,captions:el('captions').checked});download(new Blob([saved],{type:'application/json'}),'chronicle-forge-video-project.json');message('Resumable project downloaded, including completed images and audio. Keep this file private if your script is private.');
},'save'));
el('open-project').addEventListener('change',()=>busy(async()=>{
  const file=el('open-project').files[0];if(!file)return;if(file.size>70000000)throw new Error('Project exceeds the 70 MB limit');
  const loaded=loadProject(await file.text());draft=loaded.draft;project=loaded.project;clearOutput();el('narration').value=loaded.narration;el('topic').value=draft.topic;el('reviewed').checked=false;el('duration').value=draft.target_seconds||30;el('scene-count').value=loaded.options.sceneCount||Math.max(1,project.scenes.length);research={topic:draft.topic,sources:draft.sources||[]};showSources();
  for(const [id,key] of [['image-model','imageModel'],['tts-model','ttsModel'],['voice','voice'],['style','style'],['image-quality','imageQuality']]){
    if(loaded.options[key]){const option=document.createElement('option');option.value=loaded.options[key];option.textContent=loaded.options[key];el(id).append(option);el(id).value=option.value;}}
  for(const id of ['fit','resolution'])if(loaded.options[id])el(id).value=loaded.options[id];
  for(const id of ['captions','motion'])if(typeof loaded.options[id]==='boolean')el(id).checked=loaded.options[id];
  document.querySelectorAll('[name=visual-style]').forEach(x=>x.checked=x.value===el('style').value);
  project.identity=mediaIdentity(loaded.narration.trim(),settings());
  el('result').textContent=(draft.audit||'')+'\nLoaded from your saved project. Review before publishing.';renderAssets();message('Project restored without any AI calls. Review the narration; completed assets can be rendered immediately.');
},'restore'));
el('diagnostics').addEventListener('click',()=>download(new Blob([JSON.stringify(diagnostics.export(),null,2)],{type:'application/json'}),'chronicle-forge-diagnostics.json'));
window.addEventListener('beforeunload',()=>objectUrls.forEach(x=>URL.revokeObjectURL(x)));
try{anna=await AnnaAppRuntime.connect();await anna.window.set_title({title:'Chronicle Forge'});message('Connected to Anna. All AI generation uses Anna-hosted services; browser video encoding runs on this device without a local AI model.');}catch(e){message(`Open inside Anna to connect. Browser export check still works. ${e.message}`);}if(anna)await busy(catalog,'models');controls();
