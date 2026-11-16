export function imageRect(imageWidth,imageHeight,width,height,fit='contain'){
  if([imageWidth,imageHeight,width,height].some(x=>!Number.isFinite(x)||x<=0))throw new Error('Invalid image dimensions');
  const scale=(fit==='cover'?Math.max:Math.min)(width/imageWidth,height/imageHeight);
  const w=imageWidth*scale,h=imageHeight*scale;
  return {x:(width-w)/2,y:(height-h)/2,width:w,height:h};
}
