// In-memory diagnostics only. No content, identifiers, URLs or network transport.
export function createDiagnostics(){
  const events=[],stages=new Set(['research','script','media','encode','models','restore','save','thumbnail','encoder_check','operation']);
  return {
    record(stage,type,fields={}){
      const event={at:new Date().toISOString(),stage:stages.has(stage)?stage:'operation',type:['start','complete','failed','progress'].includes(type)?type:'progress'};
      for(const key of ['duration_ms','completed','total'])if(Number.isFinite(fields[key]))event[key]=Math.max(0,Math.round(fields[key]*100)/100);
      if(fields.error_code)event.error_code=['APP_NOT_GRANTED','APP_QUOTA_EXCEEDED','APP_PROVIDER_ERROR','IMAGE_CONTENT_REJECTED','AUDIO_PROVIDER_ERROR','AUDIO_MODEL_UNAVAILABLE','wait_timeout'].includes(fields.error_code)?fields.error_code:'operation_failed';
      events.push(event);if(events.length>500)events.shift();
    },
    export(){return {format:'chronicle-forge-diagnostics-v1',content_capture:false,automatic_transmission:false,events:events.map(x=>({...x}))};}
  };
}
