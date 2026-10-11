import React from 'react';

const PAPER = '#f3f4ee';
const INK = '#19221e';
const order = i => String(i + 1).padStart(2, '0');
const phase = (scene, frame, i, enter) => enter(frame, Math.min(i * 6, Math.max(0, scene.durationInFrames - 15)));

function PointText({point, light = false, compact = false}) {
  return <>
    {point.title && <div style={{fontSize: compact ? 29 : 35, fontWeight: 700, lineHeight: 1.35,
      color: light ? PAPER : INK}}>{point.title}</div>}
    {point.text && <div style={{fontSize: compact ? 22 : 25, lineHeight: 1.55,
      marginTop: point.title ? 10 : 0, color: light ? '#ccddd0' : '#405648'}}>{point.text}</div>}
  </>;
}
function Flow({scene, brand, frame, ContentBox, enter}) {
  const n = scene.points.length, columns = Math.min(n, 3), rows = Math.ceil(n / columns);
  const width = columns === 1 ? 680 : columns === 2 ? 560 : 440;
  const step = columns === 2 ? 780 : 560;
  const nodes = scene.points.map((point, i) => {
    const row = Math.floor(i / columns), col = row % 2 ? columns - 1 - i % columns : i % columns;
    const cx = 960 + (col - (columns - 1) / 2) * step;
    const cy = rows === 1 ? 565 : row === 0 ? 432 : 715;
    const height = point.text ? (rows === 1 ? 230 : 210) : point.title.length > 22 ? 164 : 116;
    return {point, i, cx, cy, width, height};
  });
  const marker = `flow-arrow-${scene.id.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  return <>
    <svg width="1920" height="1080" style={{position: 'absolute', inset: 0}}>
      <defs><marker id={marker} viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto">
        <path d="M2 2 L10 6 L2 10" fill="none" stroke={brand.accent} strokeWidth="2"/>
      </marker></defs>
      {nodes.slice(1).map((node, j) => {
        const previous = nodes[j], horizontal = previous.cy === node.cy;
        const sign = Math.sign(node.cx - previous.cx);
        const startX = horizontal ? previous.cx + sign * (previous.width / 2 + 10) : previous.cx;
        const startY = horizontal ? previous.cy : previous.cy + previous.height / 2 + 12;
        const endX = horizontal ? node.cx - sign * (node.width / 2 + 16) : node.cx;
        const endY = horizontal ? node.cy : node.cy - node.height / 2 - 18;
        return <path key={j} d={`M${startX} ${startY} L${endX} ${endY}`} fill="none" stroke={brand.accent}
          strokeWidth="4" markerEnd={`url(#${marker})`} opacity={.2 + .8 * phase(scene, frame, j + 1, enter)}/>;
      })}
    </svg>
    {nodes.map(node => {const q = phase(scene, frame, node.i, enter); return <div key={node.i}
      style={{position: 'absolute', left: node.cx - node.width / 2, top: node.cy - node.height / 2,
        width: node.width, height: node.height, borderRadius: 16, background: PAPER,
        borderTop: `5px solid ${brand.accent}`, boxShadow: '0 16px 34px #0003', opacity: q,
        transform: `translateY(${(1-q)*14}px)`}}>
      <div style={{position: 'absolute', left: 25, top: -28, background: '#11241c', border: `2px solid ${brand.accent}`,
        borderRadius: 30, color: brand.accent, padding: '6px 15px', fontSize: 23, fontWeight: 700}}>{order(node.i)}</div>
      <ContentBox label={`${scene.id} flow ${node.i+1}`} width={node.width-60} height={node.height-43}
        style={{left: 30, top: 26}}><PointText point={node.point} compact={rows > 1}/></ContentBox>
    </div>;})}
  </>;
}
function Compare({scene, brand, frame, ContentBox, enter}) {
  const split = Math.ceil(scene.points.length / 2);
  const groups = [scene.points.slice(0, split), scene.points.slice(split)];
  if (!groups[1].length) return <Flow {...{scene, brand, frame, ContentBox, enter}}/>;
  return <>
    <div style={{position: 'absolute', left: 959, top: 360, width: 2, height: 445, background: '#b8d2be45'}}/>
    <div style={{position: 'absolute', left: 920, top: 535, width: 80, textAlign: 'center', color: brand.accent,
      fontSize: 36, background: '#11241c', lineHeight: '70px'}}>↔</div>
    {groups.map((points, side) => <div key={side} style={{position: 'absolute', left: side ? 1050 : 120, top: 352, width: 750}}>
      <div style={{color: brand.accent, fontSize: 24, fontWeight: 700, letterSpacing: 3,
        borderBottom: `3px solid ${brand.accent}`, paddingBottom: 13, marginBottom: 18}}>{side ? 'B' : 'A'}</div>
      {points.map((point, j) => {const i = side ? split + j : j, q = phase(scene, frame, i, enter);
        const height = point.text ? (split > 2 ? 122 : 176) : (point.title.length > 22 ? 115 : 76);
        return <div key={j} style={{position: 'relative', height, marginBottom: 14, opacity: q,
          transform: `translateX(${(side ? 1 : -1)*(1-q)*20}px)`, background: side ? '#d5f1db' : PAPER,
          borderRadius: 10, borderLeft: `5px solid ${brand.accent}`}}>
          <ContentBox label={`${scene.id} compare ${i+1}`} width={690} height={height-24}
            style={{left: 25, top: 12}}><PointText point={point} compact={split > 2}/></ContentBox>
        </div>;
      })}
    </div>)}
  </>;
}
function Timeline({scene, brand, frame, ContentBox, enter}) {
  const n = scene.points.length, step = n === 1 ? 0 : 1520 / (n - 1);
  const width = n <= 3 ? 440 : Math.min(370, step - 35);
  return <>
    <div style={{position: 'absolute', left: 170, top: 559, width: 1580, height: 4, background: '#c6dfce55'}}/>
    <div style={{position: 'absolute', left: 1740, top: 535, color: brand.accent, fontSize: 40}}>›</div>
    {scene.points.map((point, i) => {const x = n === 1 ? 960 : 200 + i * step, above = i % 2 === 0;
      const q = phase(scene, frame, i, enter), height = above ? 168 : 205;
      // The labels are ordering marks, never inferred dates or quantitative claims.
      return <React.Fragment key={i}>
        <div style={{position: 'absolute', left: x-24, top: 536, width: 48, height: 48, borderRadius: '50%',
          background: '#11241c', border: `3px solid ${brand.accent}`, color: brand.accent, textAlign: 'center',
          lineHeight: '42px', fontSize: 22, fontWeight: 700, opacity: .3 + .7*q}}>{order(i)}</div>
        <div style={{position: 'absolute', left: x-1, top: above ? 510 : 584, width: 2, height: 26, background: brand.accent, opacity: q}}/>
        <ContentBox label={`${scene.id} timeline ${i+1}`} width={width} height={height}
          style={{left: Math.max(72, Math.min(1848-width, x-width/2)), top: above ? 338 : 620, opacity: q,
            transform: `translateY(${(1-q)*(above ? 10 : -10)}px)`}}>
          <PointText point={point} light compact={n > 3}/>
        </ContentBox>
      </React.Fragment>;
    })}
  </>;
}
function Checklist({scene, brand, frame, ContentBox, enter}) {
  const n = scene.points.length, rowHeight = Math.min(140, 500 / n), total = rowHeight * n;
  const top = 340 + (500-total)/2;
  return <>{scene.points.map((point, i) => {const q = phase(scene, frame, i, enter), height = rowHeight-12; return <div key={i}
    style={{position: 'absolute', left: 140, top: top+i*rowHeight, width: 1640, height,
      borderRadius: 10, background: '#ffffff09', borderBottom: '1px solid #c6dfce25', opacity: .3+.7*q}}>
    <div style={{position: 'absolute', left: 22, top: 17, width: 40, height: 40, borderRadius: 10,
      border: `2px solid ${brand.accent}`, background: `${brand.accent}18`}}>
      <svg width="36" height="36" viewBox="0 0 36 36"><path d="M8 18 L15 25 L28 10" pathLength="1"
        fill="none" stroke={brand.accent} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"
        strokeDasharray="1" strokeDashoffset={1-q}/></svg>
    </div>
    <ContentBox label={`${scene.id} checklist ${i+1}`} width={1510} height={height-18}
      style={{left: 91, top: 9, transform: `translateX(${(1-q)*12}px)`}}>
      <PointText point={point} light compact={n > 3}/>
    </ContentBox>
  </div>;})}</>;
}
export function DiagramLayouts(props) {
  switch (props.scene.diagramLayout) {
    case 'compare': return <Compare {...props}/>;
    case 'timeline': return <Timeline {...props}/>;
    case 'checklist': return <Checklist {...props}/>;
    default: return <Flow {...props}/>;
  }
}
