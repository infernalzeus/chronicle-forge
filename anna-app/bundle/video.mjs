import {sceneImage} from './image-job.mjs';
import {softwareRender,softwareSupport} from './software-render.mjs';
import {timelineFromDurations, captionLines, srtFromScenes} from './video-plan.mjs';

export async function checkEncoding(){softwareSupport();}

async function downloadAsset(url) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:') throw new Error('Anna returned an invalid media URL');
  const response = await fetch(url, {credentials:'omit'});
  if (!response.ok) throw new Error(`Media download failed (${response.status}); keep generated assets and retry`);
  const blob = await response.blob();
  if (blob.size > 25000000) throw new Error('Generated asset exceeds the 25 MB limit');
  return blob;
}

export async function generateMedia(anna, project, options, progress, signal, onUpdate=()=>{}) {
  const notify=(update={})=>onUpdate({...update,stage:'media',completed:project.scenes.reduce((n,s)=>n+Boolean(s.imageBlob)+Boolean(s.audioBlob),0),total:project.scenes.length*2});
  notify();
  for (let i=0; i<project.scenes.length; i++) {
    const scene = project.scenes[i];
    const cancelled = () => {if (signal?.aborted) throw new Error('Stopped. Completed assets are retained; resume to continue.');};
    cancelled();
    if (!scene.imageBlob) {
      const asset={kind:'image',index:i+1,model:options.imageModel,quality:options.imageQuality||'medium',startedAt:Date.now(),sampleEligible:!scene.imageJobId&&!scene.imageUrl};notify({asset});
      if (!scene.imageUrl) {
        progress(`Anna image ${i+1}/${project.scenes.length} — hosted model`);
        scene.imageUrl = await sceneImage(anna,scene,{prompt: `Create an illustrative documentary scene, clearly a reconstruction, not archival evidence. ${options.style === 'stickman' ? 'Simple flat stick-figure illustration, white background, bold geometric shapes.' : 'Refined editorial illustration, coherent cinematic lighting, no photorealistic claims of authenticity.'} Depict the central idea of this narration: ${scene.text}. No words, logos, watermarks or invented statistics. Wide landscape composition.`, n:1, quality:options.imageQuality||'medium', modelPreferences:{hints:[{name:options.imageModel}]}}, text=>progress(`Scene ${i+1}/${project.scenes.length} · ${text}`),signal);
      }
      try{scene.imageBlob = await downloadAsset(scene.imageUrl);}catch(e){if(scene.imageJobId)delete scene.imageUrl;throw e;}
      notify({asset:{...asset,complete:true,elapsedMs:Date.now()-asset.startedAt}});
    }
    cancelled();
    if (!scene.audioBlob) {
      const asset={kind:'voice',index:i+1,model:options.ttsModel,quality:'default',startedAt:Date.now(),sampleEligible:!scene.audioResult};notify({asset});
      if (!scene.audioResult) {
        progress(`Anna narration ${i+1}/${project.scenes.length} — hosted speech model`);
        scene.audioResult = await anna.audio.speak({text:scene.text, model:options.ttsModel, ...(options.voice ? {voice:options.voice}:{}), delivery:'inline', format:'mp3'}, {timeoutMs:150000});
      }
      const result = scene.audioResult;
      if (result.audioBase64) {
        scene.audioBlob = new Blob([Uint8Array.from(atob(result.audioBase64), c=>c.charCodeAt(0))], {type:result.mimeType || 'audio/mpeg'});
      } else if (result.url) scene.audioBlob = await downloadAsset(result.url);
      else { delete scene.audioResult; throw new Error('Anna returned no speech audio'); }
      notify({asset:{...asset,complete:true,elapsedMs:Date.now()-asset.startedAt}});
    }
  }
  return project;
}

export async function decodeProject(project) {
  const ctx = new AudioContext({sampleRate:48000}), decoded = [];
  try {
    for (const scene of project.scenes) {
      if (!scene.imageBlob || !scene.audioBlob) throw new Error('Generate all scene assets before rendering');
      const image = await createImageBitmap(scene.imageBlob);
      try {
        const audio = await ctx.decodeAudioData(await scene.audioBlob.arrayBuffer());
        decoded.push({image, audio, text:scene.text});
      } catch(e) {image.close(); throw e;}
    }
    return decoded;
  } catch(e) {decoded.forEach(x=>x.image.close()); throw e;}
  finally {await ctx.close();}
}

export async function renderMp4(decoded,options={}) {
  const result=await softwareRender(decoded,options);
  await validateVideoBlob(result.blob);
  return result;
}

export async function validateVideoBlob(blob){
  const preview=document.createElement('video'),url=URL.createObjectURL(blob);
  try{await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Video validation timed out')),10000);
    preview.onloadedmetadata=()=>{clearTimeout(timer);preview.videoWidth>0&&preview.videoHeight>0?resolve():reject(new Error('MP4 is missing its picture track; retry export with Anna visible. No new AI generation is needed.'));};
    preview.onerror=()=>{clearTimeout(timer);reject(new Error('The encoded MP4 could not be decoded'));};preview.src=url;
  });}finally{preview.removeAttribute('src');preview.load();URL.revokeObjectURL(url);}
}

export async function exportSmokeTest(progress=()=>{}) {
  const source=document.createElement('canvas');source.width=640;source.height=360;
  const ctx=source.getContext('2d');ctx.fillStyle='#163c3c';ctx.fillRect(0,0,640,360);ctx.fillStyle='#fff';ctx.font='30px system-ui';ctx.fillText('Chronicle Forge export test',65,180);
  const image=await createImageBitmap(source), audio=new AudioBuffer({length:96000,numberOfChannels:1,sampleRate:48000});
  const samples=audio.getChannelData(0);for(let i=0;i<samples.length;i++)samples[i]=Math.sin(i/48000*Math.PI*880)*.03;
  try {return await renderMp4([{image,audio,text:'Two-second video export test. No AI model was used.'}],{width:640,height:360,progress,title:'Chronicle Forge export test'});}
  finally {image.close();}
}
