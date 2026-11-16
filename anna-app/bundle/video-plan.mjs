export function planScenes(text, maxScenes = 6) {
  const clean = text.trim();
  if (!clean || clean.length > 12000) throw new Error('Narration must contain 1–12,000 characters');
  if(!Number.isInteger(maxScenes)||maxScenes<1||maxScenes>24)throw new Error('Choose 1–24 scene images');
  const words=clean.split(/\s+/),count=Math.min(maxScenes,words.length),scenes=[];
  let cursor=0;
  for(let i=0;i<count;i++){
    const remaining=count-i,target=Math.ceil((words.length-cursor)/remaining);
    let end=cursor+target;
    // Prefer a nearby sentence boundary, while keeping words for every later scene.
    if(remaining>1){
      const low=cursor+Math.max(1,Math.floor(target*.7));
      const high=Math.min(words.length-(remaining-1),cursor+Math.ceil(target*1.3));
      const boundaries=[];for(let j=low;j<=high;j++)if(/[.!?]["')]*$/.test(words[j-1]))boundaries.push(j);
      if(boundaries.length)end=boundaries.sort((a,b)=>Math.abs(a-end)-Math.abs(b-end))[0];
    }
    scenes.push({text:words.slice(cursor,end).join(' ')});cursor=end;
  }
  return scenes.filter(x => x.text).flatMap(scene => {
    // Keep speech calls under common provider limits without dropping content.
    const chunks = []; let remaining = scene.text;
    while (remaining.length > 850) {
      let cut = remaining.lastIndexOf(' ', 850);
      if (cut < 1) cut = 850;
      chunks.push({text: remaining.slice(0, cut)}); remaining = remaining.slice(cut).trimStart();
    }
    if (remaining) chunks.push({text: remaining});
    return chunks;
  });
}

export function timelineFromDurations(durations) {
  let start = 0;
  return durations.map(duration => {
    if (!Number.isFinite(duration) || duration <= 0) throw new Error('Every scene needs valid speech audio');
    const item = {start, end: start + duration, duration}; start = item.end; return item;
  });
}

export function captionLines(text, maxChars = 70) {
  const words = text.trim().split(/\s+/), lines = []; let line = '';
  for (const word of words) {
    if (line && (line + ' ' + word).length > maxChars) { lines.push(line); line = ''; }
    line += (line ? ' ' : '') + word;
  }
  if (line) lines.push(line);
  return lines;
}

export function srtFromScenes(scenes, timeline) {
  const stamp = seconds => {
    const ms = Math.round(seconds * 1000);
    return `${String(Math.floor(ms / 3600000)).padStart(2,'0')}:${String(Math.floor(ms / 60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`;
  };
  let n = 0; const out = [];
  scenes.forEach((scene, i) => {
    const lines = captionLines(scene.text), all = lines.reduce((sum, x) => sum+x.length, 0);
    let cursor = timeline[i].start;
    lines.forEach((line, j) => {
      const end = j === lines.length-1 ? timeline[i].end : cursor + timeline[i].duration*line.length/all;
      out.push(`${++n}\n${stamp(cursor)} --> ${stamp(end)}\n${line}\n`); cursor = end;
    });
  });
  return out.join('\n');
}
