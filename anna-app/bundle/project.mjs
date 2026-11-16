async function pack(blob){if(!blob)return null;const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return {type:blob.type,data:btoa(binary)};}
export function mediaIdentity(text,options){return JSON.stringify({text,imageModel:options.imageModel||'',ttsModel:options.ttsModel||'',voice:options.voice||'',style:options.style||'refined',sceneCount:options.sceneCount,imageQuality:options.imageQuality||'medium'});}
function unpack(asset,kind){if(!asset)return undefined;
  const allowed=kind==='image'?['image/png','image/jpeg','image/webp']:['audio/mpeg','audio/mp3','audio/wav','audio/x-wav','audio/ogg'];
  if(!allowed.includes(asset.type)||typeof asset.data!=='string'||asset.data.length>34000000)throw new Error('Invalid project media');
  const binary=atob(asset.data);return new Blob([Uint8Array.from(binary,c=>c.charCodeAt(0))],{type:asset.type});
}
export async function saveProject(draft,project,narration,options){
  return JSON.stringify({format:'chronicle-forge-video-project-v1',draft,narration,options,scenes:await Promise.all((project?.scenes||[]).map(async s=>({text:s.text,imageJobId:s.imageJobId,imageRequestKey:s.imageRequestKey,image:await pack(s.imageBlob),audio:await pack(s.audioBlob)})))},null,2);
}
export function loadProject(text){
  if(text.length>70000000)throw new Error('Project exceeds the 70 MB limit');
  const data=JSON.parse(text);
  if(data.format!=='chronicle-forge-video-project-v1'||!data.draft||typeof data.draft.topic!=='string'||typeof data.narration!=='string'||data.narration.length>12000||!Array.isArray(data.scenes)||data.scenes.length>60)throw new Error('Invalid Chronicle Forge video project');
  const scenes=data.scenes.map(s=>{if(typeof s.text!=='string'||!s.text.trim()||s.text.length>850)throw new Error('Invalid scene narration');return {text:s.text,imageJobId:typeof s.imageJobId==='string'?s.imageJobId:undefined,imageRequestKey:typeof s.imageRequestKey==='string'?s.imageRequestKey:undefined,imageBlob:unpack(s.image,'image'),audioBlob:unpack(s.audio,'audio')};});
  const options={...data.options,sceneCount:data.options?.sceneCount||Math.max(1,scenes.length)};
  return {draft:data.draft,narration:data.narration,options,project:{topic:data.draft.topic,identity:mediaIdentity(data.narration,options),scenes}};
}
