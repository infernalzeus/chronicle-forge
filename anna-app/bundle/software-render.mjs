import {FFmpeg} from './vendor/ffmpeg/classes.js';
import {timelineFromDurations,srtFromScenes} from './video-plan.mjs';
import {imageRect} from './framing.mjs';
let encoder,loading;
export function softwareSupport(){if(typeof Worker==='undefined'||typeof WebAssembly==='undefined')throw new Error('Video export needs a modern desktop browser with WebAssembly. No AI model was run.');}
async function getEncoder(progress){
  softwareSupport();if(encoder?.loaded)return encoder;if(loading)return loading;
  loading=(async()=>{progress('Loading software video encoder (31 MB, no AI model or Anna credits)…');const ff=new FFmpeg();
    const parts=await Promise.all([0,1,2,3,4].map(async i=>{const r=await fetch(new URL(`./vendor/ffmpeg/core-part-${i}.wasm`,import.meta.url));if(!r.ok)throw new Error('Could not load video encoder');return r.arrayBuffer();}));
    const url=URL.createObjectURL(new Blob(parts,{type:'application/wasm'}));let timeout;
    try{await Promise.race([ff.load({coreURL:new URL('./vendor/ffmpeg/ffmpeg-core.js',import.meta.url).href,wasmURL:url}),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('Video encoder startup timed out')),45000);})]);encoder=ff;return ff;}
    catch(e){ff.terminate();throw e;}finally{clearTimeout(timeout);URL.revokeObjectURL(url);}
  })();try{return await loading;}finally{loading=null;}
}
export function waveBytes(buffer){
  const length=buffer.length,channels=buffer.numberOfChannels,out=new ArrayBuffer(44+length*2),v=new DataView(out);
  const text=(offset,s)=>[...s].forEach((c,i)=>v.setUint8(offset+i,c.charCodeAt(0)));
  text(0,'RIFF');v.setUint32(4,36+length*2,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,buffer.sampleRate,true);v.setUint32(28,buffer.sampleRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,length*2,true);
  const planes=Array.from({length:channels},(_,i)=>buffer.getChannelData(i));
  for(let i=0;i<length;i++){let value=0;for(const plane of planes)value+=plane[i]/channels;value=Math.max(-1,Math.min(1,value));v.setInt16(44+i*2,Math.round(value*(value<0?32768:32767)),true);}
  return new Uint8Array(out);
}
export async function softwareRender(decoded,{width=1280,height=720,captions=true,fit='contain',motion=false,title='Chronicle Forge',progress=()=>{},signal,onProgress=()=>{}}={}){
  if(!decoded.length)throw new Error('No scenes to render');const timeline=timelineFromDurations(decoded.map(x=>x.audio.duration)),duration=timeline.at(-1).end;
  if(duration>600)throw new Error('Videos are limited to ten minutes');
  const ff=await getEncoder(progress),files=[],cancel=()=>{ff.terminate();encoder=null;};signal?.addEventListener('abort',cancel,{once:true});
  const remember=async(name,data)=>{files.push(name);await ff.writeFile(name,data);};
  let currentScene=0;const encodingProgress=({progress:ratio})=>{const fraction=Math.max(0,Math.min(1,ratio));progress(`Encoding scene ${currentScene+1}/${decoded.length} · ${Math.round(fraction*100)}%`);onProgress({stage:'encode',completed:currentScene+fraction,total:decoded.length});};ff.on('progress',encodingProgress);
  const logs=[];const log=({message})=>{logs.push(message);if(logs.length>12)logs.shift();};ff.on('log',log);
  try{
    const font=await fetch(new URL('./vendor/ffmpeg/DejaVuSans.ttf',import.meta.url));if(!font.ok)throw new Error('Caption font could not be loaded');await remember('DejaVuSans.ttf',new Uint8Array(await font.arrayBuffer()));
    const segments=[];
    for(let i=0;i<decoded.length;i++){
      if(signal?.aborted)throw new Error('Export stopped; generated assets are retained');currentScene=i;const scene=decoded[i],duration=scene.audio.duration;
      progress(`Software encoding scene ${i+1}/${decoded.length} — no local AI model`);
      const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');
      ctx.fillStyle='#101819';ctx.fillRect(0,0,width,height);
      const rect=imageRect(scene.image.width,scene.image.height,width,height,fit);
      ctx.drawImage(scene.image,rect.x,rect.y,rect.width,rect.height);
      const picture=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!picture)throw new Error('Scene image could not be prepared');
      await remember('scene.png',new Uint8Array(await picture.arrayBuffer()));await remember('speech.wav',waveBytes(scene.audio));
      await remember('captions.srt',new TextEncoder().encode(srtFromScenes([scene],timelineFromDurations([duration]))));
      const frames=Math.max(2,Math.ceil(duration*24)),zoom=`zoompan=z='1.06-0.06*on/${frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=${width}x${height}:fps=24`;
      const disclosure=`,drawtext=fontfile=DejaVuSans.ttf:text='AI ILLUSTRATION':fontcolor=white:fontsize=${Math.round(width/70)}:box=1:boxcolor=black@0.65:boxborderw=8:x=24:y=24`;
      const filters=(motion&&fit==='cover'?zoom:'null')+disclosure+(captions?",subtitles=captions.srt:fontsdir=.:force_style='FontName=DejaVu Sans,FontSize=18,Outline=2,Alignment=2,MarginV=24'":'');
      const name=`segment-${i}.mp4`;files.push(name);segments.push(name);
      const code=await ff.exec(['-loop','1','-framerate','24','-i','scene.png','-i','speech.wav','-vf',filters,'-t',duration.toFixed(6),'-r','24','-c:v','libx264','-preset','ultrafast','-crf','24','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',name],300000);
      if(code!==0)throw new Error(`Scene encoding failed: ${logs.slice(-4).join(' ')}`);
      onProgress({stage:'encode',completed:i+1,total:decoded.length});
    }
    await remember('segments.txt',new TextEncoder().encode(segments.map(x=>`file '${x}'`).join('\n')));files.push('final.mp4');
    progress('Joining picture and sound…');const code=await ff.exec(['-f','concat','-safe','0','-i','segments.txt','-c','copy','-metadata',`title=${title}`,'-movflags','+faststart','final.mp4'],120000);
    if(code!==0)throw new Error('Could not join the completed scenes');const data=await ff.readFile('final.mp4');
    return {blob:new Blob([data],{type:'video/mp4'}),duration,timeline,srt:srtFromScenes(decoded,timeline)};
  }finally{signal?.removeEventListener('abort',cancel);ff.off('log',log);ff.off('progress',encodingProgress);if(ff.loaded)for(const name of new Set(files))await ff.deleteFile(name).catch(()=>{});}
}
