import React, {useEffect, useRef, useState} from 'react';
import {AbsoluteFill, Audio, Composition, Easing, Img, OffthreadVideo, Sequence, cancelRender,
  continueRender, delayRender, interpolate, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import {getVideoMetadata} from '@remotion/media-utils';
import {BrandStamp} from './BrandStamp.jsx';
import {DiagramLayouts} from './DiagramLayouts.jsx';
import {coverPoints, fitCoverTitle} from './CoverLayout.mjs';
import regularFont from '../fonts/NotoSansSC-400.woff2';
import boldFont from '../fonts/NotoSansSC-700.woff2';

const INK = '#19221e';
const PAPER = '#f3f4ee';
const FAMILY = 'Investigation Noto';
let fontPromise;
function loadFonts() {
  return fontPromise ??= Promise.all([[regularFont, '400'], [boldFont, '700']].map(async ([url, weight]) => {
    const font = new FontFace(FAMILY, `url("${url}")`, {weight});
    await font.load(); document.fonts.add(font);
  }));
}
function Fonts() {
  const [handle] = useState(() => delayRender('Loading local Noto fonts'));
  useEffect(() => {
    loadFonts().then(() => continueRender(handle)).catch(cancelRender);
  }, [handle]);
  return null;
}
// Fit actual loaded-font content, never truncate or hide a supplied point.
// Reject text that would need illegibly small type so the pipeline can split it.
function ContentBox({label, width, height, style, children}) {
  const inner = useRef(null);
  const [scale, setScale] = useState(1);
  const [handle] = useState(() => delayRender(`Checking text layout: ${label}`));
  useEffect(() => {
    let active = true;
    loadFonts().then(() => {
      if (!active || !inner.current) return;
      const fit = Math.min(1, height / Math.max(1, inner.current.scrollHeight));
      if (fit < .66) throw new Error(`${label}: too much text for a readable layout. Split this scene or shorten its overlays.`);
      setScale(fit);
      continueRender(handle);
    }).catch(cancelRender);
    return () => {active = false; continueRender(handle);};
  }, [handle, height, label]);
  return <div style={{position: 'absolute', width, height, ...style}}><div ref={inner}
    style={{width, transform: `scale(${scale})`, transformOrigin: 'top left', overflowWrap: 'anywhere'}}>{children}</div></div>;
}
const enter = (frame, delay = 0, duration = 14) => interpolate(frame, [delay, delay + duration], [0, 1],
  {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(.18, .8, .22, 1)});
const headingSize = (text, wide = false) => text.length > 55 ? 42 : text.length > 30 ? 50 : wide ? 68 : 60;

function Texture({light = false}) {
  return <AbsoluteFill style={{pointerEvents: 'none', zIndex: 6, opacity: light ? .12 : .18,
    backgroundImage: 'radial-gradient(#83958a 0.8px, transparent 0.8px)', backgroundSize: '13px 13px',
    mixBlendMode: light ? 'multiply' : 'screen'}}/>;
}
function Source({scene, light = false}) {
  const label = [scene.sourceLabel, scene.sourceDate].filter(Boolean).join(' · ');
  return label ? <div style={{position: 'absolute', zIndex: 12, left: 72, bottom: 159,
    maxWidth: 1720, padding: '9px 14px', color: light ? '#455b4e' : '#f1f4ed',
    background: light ? '#f5f6efde' : '#10231cce', fontSize: 20, lineHeight: 1.35}}>{label}</div> : null;
}
function Caption({captions}) {
  const frame = useCurrentFrame();
  const cue = captions.find(c => frame >= c.start && frame < c.end);
  return cue ? <div style={{position: 'absolute', zIndex: 40, bottom: 34, left: 100, right: 100,
    display: 'flex', justifyContent: 'center'}}><div style={{padding: '13px 25px', color: '#fff', background: '#0c1813e8',
      borderRadius: 9, fontSize: cue.text.length > 90 ? 26 : cue.text.length > 45 ? 35 : 43, fontWeight: 700, lineHeight: 1.45,
      maxWidth: 1640, textAlign: 'center', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{cue.text}</div></div> : null;
}
function VideoLayer({scene, style}) {
  return <OffthreadVideo src={staticFile(scene.media)} startFrom={scene.mediaStart} muted
    style={{position: 'absolute', ...style}}/>;
}
function FilmScene({scene, brand}) {
  const frame = useCurrentFrame();
  const q = enter(frame);
  const portrait = scene.layout === 'portrait' || (scene.layout === 'auto' && scene.mediaAspect < 1);
  const collage = portrait || scene.layout === 'collage';
  return <AbsoluteFill style={{background: '#11241b'}}>
    {collage ? <>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 25% 30%,#375a48,transparent 75%)'}}/>
      <div style={{position: 'absolute', left: 95, top: 135, width: portrait ? 790 : 1060, height: 745,
        border: '8px solid #f2f2e8', boxShadow: '14px 26px 44px #0007', transform: `rotate(-1.1deg) translateY(${(1-q)*22}px)`}}>
        <VideoLayer scene={scene} style={{width: '100%', height: '100%', objectFit: 'contain', background: '#17241c'}}/>
      </div>
      <ContentBox label={`${scene.id} video overlay`} width={portrait ? 865 : 590} height={625}
        style={{left: portrait ? 970 : 1245, top: 226, color: PAPER}}>
        <Badge text={scene.badge} accent={brand.accent}/>
        <div style={{fontSize: headingSize(scene.heading), fontWeight: 700, lineHeight: 1.4, marginTop: 20}}>{scene.heading}</div>
        {scene.text && <div style={{fontSize: 28, lineHeight: 1.7, marginTop: 30, color: '#d5e0d6'}}>{scene.text}</div>}
        {scene.speaker && <div style={{fontSize: 22, marginTop: 28, color: '#bccfc0'}}>{scene.speaker}</div>}
      </ContentBox>
    </> : <>
      <VideoLayer scene={scene} style={{inset: 0, width: '100%', height: '100%', objectFit: 'cover'}}/>
      <AbsoluteFill style={{background: 'linear-gradient(180deg,#061b11c9 0%,transparent 40%,transparent 62%,#07150ef2 100%)'}}/>
      <div style={{position: 'absolute', left: 76, right: 570, top: 80, color: '#fff', opacity: q,
        transform: `translateY(${(1-q)*16}px)`}}><Badge text={scene.badge} accent={brand.accent}/>
        <div style={{fontSize: headingSize(scene.heading, true), fontWeight: 700, lineHeight: 1.25, marginTop: 18,
          textShadow: '0 3px 16px #0008'}}>{scene.heading}</div>
      </div>
      {(scene.text || scene.speaker) && <div style={{position: 'absolute', left: 84, right: 150, bottom: 222, color: PAPER,
        fontSize: 31, lineHeight: 1.5, maxWidth: 1450}}>{scene.text || scene.speaker}</div>}
    </>}
    <Source scene={scene}/>
  </AbsoluteFill>;
}
function Badge({text, accent}) {
  return text ? <div style={{display: 'inline-block', background: accent, color: '#10251b', fontSize: 23,
    fontWeight: 700, padding: '8px 15px', letterSpacing: 2}}>{text}</div> : null;
}
function DocumentScene({scene, brand}) {
  const frame = useCurrentFrame(), q = enter(frame);
  const evidence = scene.kind === 'evidence';
  if (!scene.media) return <TextScene scene={scene} brand={brand} evidence/>;
  return <AbsoluteFill style={{background: '#e4e9e1'}}>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 25% 15%,#ffffffed,transparent 68%)'}}/>
    <div style={{position: 'absolute', left: 83, top: 164, width: 1040, height: 688,
      background: '#fafbf6', border: '14px solid #fafbf6', boxShadow: '14px 26px 36px #263c3335',
      transform: `translateX(${(1-q)*-32}px) rotate(${evidence ? -1.1 : -1.8}deg)`}}>
      <Img src={staticFile(scene.media)} style={{width: '100%', height: '100%', objectFit: 'contain'}}/>
      {evidence && <div style={{position: 'absolute', top: -30, left: 400, width: 220, height: 42,
        background: '#b0c5b6bb', transform: 'rotate(3deg)'}}/>}
    </div>
    <ContentBox label={`${scene.id} document overlay`} width={638} height={650} style={{left: 1200, top: 194, color: INK}}>
      <Badge text={scene.badge || (evidence ? '证据与来源' : '')} accent={brand.accent}/>
      <div style={{fontSize: headingSize(scene.heading), lineHeight: 1.3, fontWeight: 700, marginTop: 22}}>{scene.heading}</div>
      <div style={{height: 7, background: brand.accent, width: 116, margin: '25px 0'}}/>
      {scene.text && <div style={{fontSize: scene.text.length > 140 ? 24 : 29, lineHeight: 1.75}}>{scene.text}</div>}
      {scene.points.length > 0 && <div style={{marginTop: 24, display: 'grid', gap: 16}}>{scene.points.map((p, i) =>
        <div key={i} style={{fontSize: 25, lineHeight: 1.5, borderLeft: `4px solid ${brand.accent}`, paddingLeft: 14}}>{p.title}{p.text && `：${p.text}`}</div>)}</div>}
    </ContentBox>
    <Texture light/><Source scene={scene} light/>
  </AbsoluteFill>;
}
function TextScene({scene, brand, evidence = false}) {
  return <AbsoluteFill style={{background: evidence ? '#e4e9e1' : '#11241c', color: evidence ? INK : PAPER}}>
    <ContentBox label={`${scene.id} text`} width={1680} height={718} style={{left: 120, top: 138}}>
      <Badge text={scene.badge || (evidence ? '原文摘录 · 文字整理' : '机制说明')} accent={brand.accent}/>
      <div style={{fontSize: headingSize(scene.heading, true), fontWeight: 700, lineHeight: 1.3, marginTop: 24}}>{scene.heading}</div>
      <div style={{fontSize: scene.text.length > 600 ? 25 : scene.text.length > 250 ? 31 : 42, lineHeight: 1.65,
        marginTop: 30, whiteSpace: 'pre-wrap', borderLeft: `6px solid ${brand.accent}`, paddingLeft: 30}}>{scene.text}</div>
    </ContentBox>
    <Texture light={evidence}/><Source scene={scene} light={evidence}/>
  </AbsoluteFill>;
}
function DiagramScene({scene, brand}) {
  const frame = useCurrentFrame();
  if (!scene.points.length) return <TextScene scene={scene} brand={brand}/>;
  return <AbsoluteFill style={{background: '#11241c'}}>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 12% 0%,#355747,transparent 70%)'}}/>
    <ContentBox label={`${scene.id} diagram heading`} width={1268} height={238} style={{left: 82, top: 83, color: PAPER}}>
      <Badge text={scene.badge || '机制说明'} accent={brand.accent}/>
      <div style={{fontSize: headingSize(scene.heading, true), fontWeight: 700, lineHeight: 1.3, marginTop: 17}}>{scene.heading}</div>
      {scene.text && <div style={{fontSize: 27, color: '#c3d2c7', marginTop: 18, lineHeight: 1.6}}>{scene.text}</div>}
    </ContentBox>
    <DiagramLayouts scene={scene} brand={brand} frame={frame} ContentBox={ContentBox} enter={enter}/>
    <Texture/><Source scene={scene}/>
  </AbsoluteFill>;
}
function Film(props) {
  const frame = useCurrentFrame();
  const current = props.scenes.find(s => frame >= s.startFrame && frame < s.startFrame + s.durationInFrames);
  return <AbsoluteFill style={{background: INK, fontFamily: FAMILY, overflow: 'hidden'}}>
    <Fonts/>
    <div style={{position: 'absolute', width: 1920, height: 1080, transform: `scale(${props.width/1920})`, transformOrigin: 'top left'}}>
      {props.scenes.map(scene => <Sequence key={scene.id} from={scene.startFrame} durationInFrames={scene.durationInFrames}>
        {scene.kind === 'video' ? <FilmScene scene={scene} brand={props.brand}/> : scene.kind === 'diagram'
          ? <DiagramScene scene={scene} brand={props.brand}/> : <DocumentScene scene={scene} brand={props.brand}/>}
      </Sequence>)}
      <BrandStamp brand={props.brand} dark={!['image', 'evidence'].includes(current?.kind)}/><Caption captions={props.captions}/>
    </div>
    {props.withAudio && props.narration && <Audio src={staticFile(props.narration)}/>}
  </AbsoluteFill>;
}
function Cover(props) {
  const portrait = props.coverRatio === '3:4';
  const scene = props.scenes.find(s => s.media && (s.kind === 'image' || s.kind === 'evidence'))
    ?? props.scenes.find(s => s.media && s.kind === 'video');
  const {scene: diagram, points} = coverPoints(props.scenes);
  const width = portrait ? 1080 : 1440, height = portrait ? 1440 : 1080;
  const titleWidth = portrait ? 944 : scene ? 740 : 530;
  const titleTop = portrait ? 204 : scene ? 291 : 236;
  const titleHeight = portrait ? (scene ? 440 : 308) : scene ? 520 : 430;
  const [titleLayout, setTitleLayout] = useState(null);
  const [titleHandle] = useState(() => delayRender('Balancing cover title by Chinese word boundaries'));
  useEffect(() => {
    let active = true;
    loadFonts().then(() => {
      if (!active) return;
      const context = document.createElement('canvas').getContext('2d');
      if (!context) throw new Error('Canvas text measurement unavailable for cover title');
      const measured = fitCoverTitle(props.title, {width: titleWidth, height: titleHeight,
        maxFont: portrait ? 86 : scene ? 82 : 74, measure: (text, size) => {
          context.font = `700 ${size}px "${FAMILY}"`;
          return context.measureText(text).width;
        }});
      setTitleLayout(measured); continueRender(titleHandle);
    }).catch(cancelRender);
    return () => {active = false; continueRender(titleHandle);};
  }, [props.title, titleWidth, titleHeight, portrait, Boolean(scene), titleHandle]);
  const panel = portrait ? {left: 64, top: 682, width: 952, height: 610}
    : {left: 666, top: 184, width: 706, height: 752};
  const columns = portrait && points.length === 4 ? 2 : 1;
  const rows = Math.ceil(points.length / columns) || 1;
  const cardGap = portrait ? 18 : 14;
  const cardWidth = (panel.width - 64 - (columns - 1) * cardGap) / columns;
  const cardHeight = (panel.height - 130 - (rows - 1) * cardGap) / rows;
  const subtitle = props.coverSubtitle || (!scene ? diagram?.text : '');
  return <AbsoluteFill style={{background: '#10251a', color: PAPER, fontFamily: FAMILY, overflow: 'hidden'}}>
    <Fonts/>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 15% 8%,#355747aa,transparent 65%)'}}/>
    {scene && <div style={{position: 'absolute', left: portrait ? 60 : 630, top: portrait ? 490 : 140,
      width: portrait ? 960 : 760, height: portrait ? 810 : 790, transform: 'rotate(2deg)', border: '9px solid #edf2e7', boxShadow: '0 28px 60px #0008'}}>
      {scene.kind === 'video' ? <VideoLayer scene={scene} style={{width: '100%', height: '100%', objectFit: 'cover'}}/>
        : <Img src={staticFile(scene.media)} style={{width: '100%', height: '100%', objectFit: 'cover'}}/>}
    </div>}
    <AbsoluteFill style={{background: portrait ? 'linear-gradient(#10251a 0%,#10251a88 37%,transparent 65%)' : 'linear-gradient(90deg,#10251a 15%,#10251acc 44%,transparent 77%)'}}/>
    <div style={{position: 'absolute', left: 68, top: titleTop - 58, display: 'flex', gap: 14, alignItems: 'center'}}>
      <span style={{width: 10, height: 25, background: props.brand.accent}}/>
      <span style={{fontSize: 24, fontWeight: 700, color: props.brand.accent, letterSpacing: 4}}>调查与解释</span>
    </div>
    {titleLayout && <div style={{position: 'absolute', left: 68, top: titleTop, width: titleWidth,
      fontSize: titleLayout.fontSize, fontWeight: 700, lineHeight: titleLayout.lineHeight,
      textShadow: '0 5px 26px #0007'}}>{titleLayout.lines.map((line, i) =>
        <div key={i} style={{whiteSpace: 'nowrap'}}>{line}</div>)}
    </div>}
    {subtitle && titleLayout && <ContentBox label="cover subtitle" width={titleWidth} height={portrait ? 116 : 145}
      style={{left: 68, top: titleTop + titleLayout.height + 26}}>
      <div style={{fontSize: 27, lineHeight: 1.55, color: '#bed2c4'}}>{subtitle}</div>
    </ContentBox>}
    {!scene && <div style={{position: 'absolute', ...panel, border: '1px solid #a5bdaa55',
      borderRadius: 24, background: 'linear-gradient(145deg,#edf2e9,#dfe9de)',
      color: INK, boxShadow: '0 24px 60px #0004'}}>
      <div style={{position: 'absolute', top: 26, left: 32, right: 32, display: 'flex', gap: 12, alignItems: 'center'}}>
        <div style={{width: 7, height: 27, background: props.brand.accent, flexShrink: 0}}/>
        <div style={{fontSize: 26, lineHeight: 1.35, fontWeight: 700}}>{diagram?.heading && diagram.heading.length <= 32 ? diagram.heading : '内容提要'}</div>
      </div>
      {points.length > 0 ? points.map((point, i) => {
        const x = 32 + (i % columns) * (cardWidth + cardGap);
        const y = 90 + Math.floor(i / columns) * (cardHeight + cardGap);
        // A cover is a contents preview: retain every selected point's heading,
        // and only add its explanation when short enough for the thumbnail.
        const pointTitle = point.title || point.text;
        const pointTitleSize = pointTitle.length > 24 ? 26 : portrait ? 29 : 30;
        const detailSize = portrait ? 23 : 24;
        const textWidth = cardWidth - 106;
        const titleEstimate = Math.ceil(pointTitle.length * pointTitleSize / textWidth) * pointTitleSize * 1.35;
        const detailEstimate = Math.ceil(point.text.length * detailSize / textWidth) * detailSize * 1.5;
        const showDetail = point.title && point.text && titleEstimate + detailEstimate + 10 <= cardHeight - 40;
        return <div key={i} style={{position: 'absolute', left: x, top: y, width: cardWidth, height: cardHeight,
          borderRadius: 16, background: '#fbfcf7', border: '1px solid #97ac9944', boxShadow: '0 6px 15px #254b3012'}}>
          <div style={{position: 'absolute', left: 20, top: 22, width: 42, height: 42, borderRadius: 13,
            display: 'flex', alignItems: 'center', justifyContent: 'center', background: props.brand.accent,
            fontSize: 21, fontWeight: 700, color: '#10251a'}}>{String(i + 1).padStart(2, '0')}</div>
          <ContentBox label={`cover point ${i + 1}`} width={cardWidth - 106} height={cardHeight - 40}
            style={{left: 82, top: 20}}>
            <div style={{fontSize: pointTitleSize, fontWeight: 700, lineHeight: 1.35}}>{pointTitle}</div>
            {showDetail && <div style={{fontSize: detailSize, lineHeight: 1.5, color: '#53685a', marginTop: 10}}>{point.text}</div>}
          </ContentBox>
        </div>;
      }) : <ContentBox label="cover diagram summary" width={panel.width - 88} height={panel.height - 170}
        style={{left: 44, top: 120}}><div style={{fontSize: 36, lineHeight: 1.65}}>{diagram?.text || props.coverSubtitle || props.title}</div></ContentBox>}
    </div>}
    <div style={{position: 'absolute', left: 70, bottom: 74, width: width-140, height: 7, background: props.brand.accent}}/>
    <BrandStamp brand={props.brand} top={46} right={58}/>
    <Texture/>
  </AbsoluteFill>;
}

const defaults = {title: '', brand: {signature: 'AI Video', accent: '#10C46F'}, scenes: [], captions: [],
  durationInFrames: 30, width: 1920, height: 1080, fps: 30};
async function metadata({props}) {
  const infos = new Map();
  for (const scene of props.scenes) {
    if (scene.kind !== 'video') continue;
    let info = infos.get(scene.media);
    if (!info) {info = await getVideoMetadata(staticFile(scene.media)); infos.set(scene.media, info);}
    const required = (scene.mediaStart + scene.durationInFrames) / props.fps;
    if (required > info.durationInSeconds + .5/props.fps) {
      throw new Error(`${scene.id}: video too short (${info.durationInSeconds}s < ${required}s). No automatic looping.`);
    }
    scene.mediaAspect = info.aspectRatio;
  }
  return {durationInFrames: props.durationInFrames, fps: props.fps, width: props.width, height: props.height, props};
}
registerRoot(() => <>
  <Composition id="Investigation" component={Film} width={1920} height={1080} fps={30} durationInFrames={30}
    defaultProps={defaults} calculateMetadata={metadata}/>
  <Composition id="InvestigationCover" component={Cover} width={1080} height={1440} fps={30} durationInFrames={1}
    defaultProps={{...defaults, coverRatio: '3:4'}} calculateMetadata={({props}) => ({
      durationInFrames: 1, fps: 30, width: props.coverRatio === '3:4' ? 1080 : 1440,
      height: props.coverRatio === '3:4' ? 1440 : 1080, props})}/>
</>);
