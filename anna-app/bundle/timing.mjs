// Local timing samples only: no prompts, source text, media or remote telemetry.
export function timingHistory(storage){
  let samples={};try{samples=JSON.parse(storage?.getItem('chronicle-forge-timings-v1')||'{}');}catch{}if(!samples||typeof samples!=='object'||Array.isArray(samples))samples={};
  const key=(kind,model,quality)=>JSON.stringify([kind,model||'default',quality||'default']);
  return {
    record(kind,model,quality,ms){
      if(!Number.isFinite(ms)||ms<100||ms>3600000)return;
      const k=key(kind,model,quality),previous=Array.isArray(samples[k])?samples[k]:[];
      samples[k]=[...previous.filter(x=>Number.isFinite(x)&&x>0),ms].slice(-20);
      try{storage?.setItem('chronicle-forge-timings-v1',JSON.stringify(samples));}catch{}
    },
    average(kind,model,quality){const values=samples[key(kind,model,quality)];if(!Array.isArray(values)||!values.length)return null;const valid=values.filter(x=>Number.isFinite(x)&&x>0);return valid.length?{ms:valid.reduce((a,b)=>a+b,0)/valid.length,count:valid.length}:null;}
  };
}
export function formatTime(ms){const seconds=Math.max(0,Math.round(ms/1000));return seconds<60?`${seconds}s`:`${Math.floor(seconds/60)}m ${seconds%60}s`;}
export function quotaFailure(error){return /quota|insufficient.*credit|credit.*exhaust|usage.*limit/i.test(`${error?.code||''} ${error?.message||''}`);}
