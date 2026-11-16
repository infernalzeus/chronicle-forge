// Keep the same paid job across retries; polling never creates a second image.
export async function sceneImage(anna,scene,args,progress,signal,{pollMs=2000,timeoutMs=600000}={}){
  if(!scene.imageRequestKey)scene.imageRequestKey=crypto.randomUUID();
  if(!scene.imageJobId){
    const created=await anna.image.generateAsync({...args,idempotencyKey:scene.imageRequestKey});
    scene.imageJobId=created.jobId;
    if(!scene.imageJobId)throw new Error('Anna returned no image job identifier');
  }
  const started=Date.now();
  while(true){
    if(signal?.aborted)throw new Error('Stopped waiting. The image job is retained; resume to retrieve it without a second charge.');
    const job=await anna.image.getJob({jobId:scene.imageJobId});
    if(job.state==='succeeded'){
      const image=job.result?.images?.[0];
      if(!image?.url)throw new Error('The completed image is unavailable. Save your project and contact Anna support.');
      scene.imageModel=job.model;return image.url;
    }
    if(['failed','cancelled','expired'].includes(job.state)){
      delete scene.imageJobId;delete scene.imageRequestKey;
      throw new Error(`Anna image ${job.state}: ${job.error?.message||job.error?.code||'No image was produced'}`);
    }
    progress(`Image ${job.state||'queued'}${job.progress?.queuePosition!=null?` · queue position ${job.progress.queuePosition}`:''} · ${Math.round((Date.now()-started)/1000)}s elapsed. You can stop waiting and resume this same job.`);
    if(Date.now()-started>=timeoutMs)throw new Error('Image is taking longer than expected. Resume to check the same job; no new image will be purchased.');
    await new Promise(resolve=>setTimeout(resolve,pollMs));
  }
}
